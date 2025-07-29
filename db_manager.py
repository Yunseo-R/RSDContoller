"""
RSD 모니터링 시스템 데이터베이스 관리자
PostgreSQL 연결, 기기 목록, 센싱값 데이터, 아크 알림 관리
점검 포인트 준수 및 log.py 변경사항 반영
"""

import asyncio
import asyncpg
import logging
from typing import List, Dict, Any, Optional
from datetime import datetime
from dataclasses import dataclass

import os
import csv

from config_manager import DatabaseConfig

logger = logging.getLogger(__name__)


# =============================================================================
# 데이터 클래스들
# =============================================================================

@dataclass
class ChannelData:
    """개별 채널 데이터"""
    channel_no: int
    temperature: float
    current: float
    is_arc: bool
    arc_frequency: int = 0
    arc_count: int = 0


@dataclass
class RSDSensorData:
    """RSD 센서 데이터"""
    string_id: int
    rsd_id: int
    rsd_status: int
    channels: List[ChannelData]
    timestamp: datetime


@dataclass
class StringInfo:
    """String 정보"""
    string_id: int
    static_ip: str
    rsd_count: int
    description: str
    use_yn: str


@dataclass
class DeviceInfo:
    """RSD 장치 정보"""
    string_id: int
    rsd_id: int
    device_name: str
    channel_count: int
    use_yn: str


# =============================================================================
# 데이터베이스 연결 클래스
# =============================================================================

class DatabaseConnection:
    """데이터베이스 연결 관리자"""
    
    def __init__(self, config: DatabaseConfig):
        """
        데이터베이스 연결 초기화
        
        Args:
            config: 데이터베이스 설정
        """
        self.config = config
        self._pool: Optional[asyncpg.Pool] = None
        self.is_connected = False
    
    async def connect(self) -> bool:
        """
        데이터베이스 연결 풀 생성
        
        Returns:
            연결 성공 여부
        """
        try:
            self._pool = await asyncpg.create_pool(
                host=self.config.host,
                port=self.config.port,
                database=self.config.database,
                user=self.config.username,
                password=self.config.password,
                min_size=1,
                max_size=10,
                command_timeout=30
            )
            
            self.is_connected = True
            logger.info(f"데이터베이스 연결 성공: {self.config.host}:{self.config.port}/{self.config.database}")
            return True
            
        except Exception as e:
            logger.error(f"데이터베이스 연결 실패: {e}")
            self.is_connected = False
            return False
    
    async def disconnect(self) -> None:
        """데이터베이스 연결 종료"""
        if self._pool:
            await self._pool.close()
            self._pool = None
        self.is_connected = False
        logger.info("데이터베이스 연결 종료")
    
    async def test_connection(self) -> bool:
        """연결 테스트"""
        try:
            if not self._pool:
                return False
                
            async with self._pool.acquire() as conn:
                result = await conn.fetchval("SELECT 1")
                return result == 1
                
        except Exception as e:
            logger.error(f"연결 테스트 실패: {e}")
            return False
    
    async def execute_query(self, query: str, *args) -> List[Dict[str, Any]]:
        """
        SELECT 쿼리 실행
        
        Args:
            query: SQL 쿼리
            *args: 쿼리 파라미터
            
        Returns:
            쿼리 결과
        """
        try:
            async with self._pool.acquire() as conn:
                rows = await conn.fetch(query, *args)
                return [dict(row) for row in rows]
                
        except Exception as e:
            logger.error(f"쿼리 실행 실패: {e}")
            raise
    
    async def execute_command(self, query: str, *args) -> str:
        """
        INSERT/UPDATE/DELETE 쿼리 실행
        
        Args:
            query: SQL 쿼리
            *args: 쿼리 파라미터
            
        Returns:
            실행 결과 상태
        """
        try:
            async with self._pool.acquire() as conn:
                result = await conn.execute(query, *args)
                return result
                
        except Exception as e:
            logger.error(f"명령 실행 실패: {e}")
            raise
    
    async def execute_many(self, query: str, args_list: List[tuple]) -> None:
        """
        배치 명령 실행
        
        Args:
            query: SQL 쿼리
            args_list: 파라미터 리스트
        """
        try:
            async with self._pool.acquire() as conn:
                await conn.executemany(query, args_list)
                
        except Exception as e:
            logger.error(f"배치 명령 실행 실패: {e}")
            raise


# =============================================================================
# 센서 데이터 저장소 클래스
# =============================================================================

class SensorDataRepository:
    """센서 데이터 저장소"""
    
    def __init__(self, connection: DatabaseConnection):
        """
        센서 데이터 저장소 초기화
        
        Args:
            connection: 데이터베이스 연결
        """
        self.connection = connection
    
    async def save_sensor_data(self, sensor_data: RSDSensorData) -> bool:
        """
        센서 데이터 저장
        
        Args:
            sensor_data: 저장할 센서 데이터
            
        Returns:
            저장 성공 여부
        """
        try:
            for channel in sensor_data.channels:
                insert_query = """
                INSERT INTO TB_RSD_DATA3 (
                    string_id, rsd_id, channel_no, rsd_status, 
                    temperature, current, is_arc, arc_frequency, arc_count,
                    arc_date, recv_time
                ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11)
                """
                
                arc_date = sensor_data.timestamp if channel.is_arc else None
                
                await self.connection.execute_command(
                    insert_query,
                    sensor_data.string_id,
                    sensor_data.rsd_id,
                    channel.channel_no,
                    sensor_data.rsd_status,
                    channel.temperature,
                    channel.current,
                    channel.is_arc,
                    channel.arc_frequency,
                    channel.arc_count,
                    arc_date,
                    sensor_data.timestamp
                )
            
            return True
            
        except Exception as e:
            logger.error(f"센서 데이터 저장 실패 - String {sensor_data.string_id}, RSD {sensor_data.rsd_id}: {e}")
            return False
    
    async def save_sensor_data_batch(self, sensor_data_list: List[RSDSensorData]) -> Dict[str, int]:
        """
        센서 데이터 배치 저장
        
        Args:
            sensor_data_list: 저장할 센서 데이터 리스트
            
        Returns:
            저장 결과 딕셔너리
        """
        if not sensor_data_list:
            return {
                'total_count': 0,
                'success_count': 0,
                'error_count': 0
            }
        
        try:
            # 배치 데이터 준비
            batch_data = []
            for sensor_data in sensor_data_list:
                for channel in sensor_data.channels:
                    arc_date = sensor_data.timestamp if channel.is_arc else None
                    batch_data.append((
                        sensor_data.string_id,
                        sensor_data.rsd_id,
                        channel.channel_no,
                        sensor_data.rsd_status,
                        channel.temperature,
                        channel.current,
                        channel.is_arc,
                        channel.arc_frequency,
                        channel.arc_count,
                        arc_date,
                        sensor_data.timestamp
                    ))
            
            # 배치 실행
            insert_query = """
            INSERT INTO TB_RSD_DATA3 (
                string_id, rsd_id, channel_no, rsd_status, 
                temperature, current, is_arc, arc_frequency, arc_count,
                arc_date, recv_time
            ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11)
            """
            
            await self.connection.execute_many(insert_query, batch_data)
            
            return {
                'total_count': len(sensor_data_list),
                'success_count': len(sensor_data_list),
                'error_count': 0
            }
            
        except Exception as e:
            logger.error(f"배치 센서 데이터 저장 실패: {e}")
            return {
                'total_count': len(sensor_data_list),
                'success_count': 0,
                'error_count': len(sensor_data_list)
            }


# =============================================================================
# 장치 정보 저장소 클래스
# =============================================================================

class DeviceRepository:
    """장치 정보 저장소"""
    
    def __init__(self, connection: DatabaseConnection):
        """
        장치 정보 저장소 초기화
        
        Args:
            connection: 데이터베이스 연결
        """
        self.connection = connection
    
    async def get_active_strings(self) -> List[StringInfo]:
        """
        활성 String 목록 조회
        
        Returns:
            활성 String 정보 리스트
        """
        try:
            query = """
            SELECT string_id, static_ip, rsd_count, description, use_yn
            FROM TB_STRING 
            WHERE use_yn = 'Y' AND del_yn = 'N'
            ORDER BY string_id
            """
            
            result = await self.connection.execute_query(query)
            
            return [
                StringInfo(
                    string_id=row['string_id'],
                    static_ip=row['static_ip'],
                    rsd_count=row['rsd_count'],
                    description=row['description'],
                    use_yn=row['use_yn']
                )
                for row in result
            ]
            
        except Exception as e:
            logger.error(f"활성 String 조회 실패: {e}")
            return []
    
    async def get_active_devices_by_string(self, string_id: int) -> List[DeviceInfo]:
        """
        특정 String의 활성 RSD 목록 조회
        
        Args:
            string_id: String ID
            
        Returns:
            RSD 정보 리스트
        """
        try:
            query = """
            SELECT string_id, rsd_id, device_name, channel_count, use_yn
            FROM TB_DEVICE3 
            WHERE string_id = $1 AND use_yn = 'Y' AND del_yn = 'N'
            ORDER BY rsd_id
            """
            
            result = await self.connection.execute_query(query, string_id)
            
            return [
                DeviceInfo(
                    string_id=row['string_id'],
                    rsd_id=row['rsd_id'],
                    device_name=row['device_name'],
                    channel_count=row['channel_count'],
                    use_yn=row['use_yn']
                )
                for row in result
            ]
            
        except Exception as e:
            logger.error(f"String {string_id}의 RSD 조회 실패: {e}")
            return []
    
    async def get_all_active_devices(self) -> List[DeviceInfo]:
        """
        모든 활성 RSD 목록 조회
        
        Returns:
            모든 RSD 정보 리스트
        """
        try:
            query = """
            SELECT string_id, rsd_id, device_name, channel_count, use_yn
            FROM TB_DEVICE3 
            WHERE use_yn = 'Y' AND del_yn = 'N'
            ORDER BY string_id, rsd_id
            """
            
            result = await self.connection.execute_query(query)
            
            return [
                DeviceInfo(
                    string_id=row['string_id'],
                    rsd_id=row['rsd_id'],
                    device_name=row['device_name'],
                    channel_count=row['channel_count'],
                    use_yn=row['use_yn']
                )
                for row in result
            ]
            
        except Exception as e:
            logger.error(f"모든 활성 RSD 조회 실패: {e}")
            return []
    
    async def get_string_info(self, string_id: int) -> Optional[StringInfo]:
        """
        특정 String 정보 조회
        
        Args:
            string_id: String ID
            
        Returns:
            String 정보 또는 None
        """
        try:
            query = """
            SELECT string_id, static_ip, rsd_count, description, use_yn
            FROM TB_STRING 
            WHERE string_id = $1 AND del_yn = 'N'
            """
            
            result = await self.connection.execute_query(query, string_id)
            
            if result:
                row = result[0]
                return StringInfo(
                    string_id=row['string_id'],
                    static_ip=row['static_ip'],
                    rsd_count=row['rsd_count'],
                    description=row['description'],
                    use_yn=row['use_yn']
                )
            
            return None
            
        except Exception as e:
            logger.error(f"String {string_id} 정보 조회 실패: {e}")
            return None


# =============================================================================
# 알림 저장소 클래스
# =============================================================================

class AlertRepository:
    """알림 저장소"""
    
    def __init__(self, connection: DatabaseConnection):
        """
        알림 저장소 초기화
        
        Args:
            connection: 데이터베이스 연결
        """
        self.connection = connection
    
    async def save_alert(self, string_id: int, rsd_id: int, log_type: int, 
                        description: str, channel_no: Optional[int] = None) -> bool:
        """
        알림 저장
        
        Args:
            string_id: String ID
            rsd_id: RSD ID  
            log_type: 알림 타입 (1: 아크 발생, 2: 통신 오류, 3: 시스템 오류)
            description: 알림 설명
            channel_no: 채널 번호 (선택사항)
            
        Returns:
            저장 성공 여부
        """
        try:
            insert_query = """
            INSERT INTO TB_ALERT_LOG3 (
                string_id, rsd_id, log_type, log_title, log_content, reg_date
            ) VALUES ($1, $2, $3, $4, $5, $6)
            """
            
            # log_title과 log_content 구성
            if channel_no:
                log_title = f"채널 {channel_no} 알림"
            else:
                log_title = "시스템 알림"
            
            await self.connection.execute_command(
                insert_query,
                string_id,
                rsd_id,
                log_type,
                log_title,
                description,
                datetime.now()
            )
            
            logger.info(f"알림 저장 완료 - String {string_id}, RSD {rsd_id}: {description}")
            return True
            
        except Exception as e:
            logger.error(f"알림 저장 실패 - String {string_id}, RSD {rsd_id}: {e}")
            return False
    
    async def save_arc_alert(self, string_id: int, rsd_id: int, channel_no: int, 
                           arc_frequency: int, arc_count: int) -> bool:
        """
        아크 발생 알림 저장 (아크 주파수 기반)
        
        Args:
            string_id: String ID
            rsd_id: RSD ID
            channel_no: 채널 번호
            arc_frequency: 아크 주파수 (Hz)
            arc_count: 감지 횟수
            
        Returns:
            저장 성공 여부
        """
        description = f"아크 발생 감지 - CH{channel_no} ({arc_frequency} KHz / {arc_count}회)"
        return await self.save_alert(string_id, rsd_id, 1, description, channel_no)
    
    async def save_communication_error_alert(self, string_id: int, rsd_id: int, 
                                           error_message: str) -> bool:
        """
        통신 오류 알림 저장
        
        Args:
            string_id: String ID
            rsd_id: RSD ID
            error_message: 오류 메시지
            
        Returns:
            저장 성공 여부
        """
        description = f"통신 오류: {error_message}"
        return await self.save_alert(string_id, rsd_id, 2, description)
    
    async def get_recent_alerts(self, limit: int = 100) -> List[Dict[str, Any]]:
        """
        최근 알림 목록 조회
        
        Args:
            limit: 조회할 알림 수
            
        Returns:
            알림 리스트
        """
        try:
            query = """
            SELECT string_id, rsd_id, log_type, log_title, log_content, reg_date
            FROM TB_ALERT_LOG3 
            ORDER BY reg_date DESC 
            LIMIT $1
            """
            
            return await self.connection.execute_query(query, limit)
            
        except Exception as e:
            logger.error(f"최근 알림 조회 실패: {e}")
            return []
        

    async def save_communication_error_alert(self, string_id: int, rsd_id: int, 
                                           error_message: str) -> bool:
        """
        통신 오류 알림 저장
        
        Args:
            string_id: String ID
            rsd_id: RSD ID
            error_message: 오류 메시지
            
        Returns:
            저장 성공 여부
        """
        description = f"통신 오류: {error_message}"
        return await self.save_alert(string_id, rsd_id, 2, description)
    
    async def save_system_error_alert(self, component: str, error_message: str, 
                                    string_id: Optional[int] = None, 
                                    rsd_id: Optional[int] = None) -> bool:
        """
        시스템 오류 알림 저장
        
        Args:
            component: 오류 발생 컴포넌트
            error_message: 오류 메시지
            string_id: String ID (선택사항)
            rsd_id: RSD ID (선택사항)
            
        Returns:
            저장 성공 여부
        """
        description = f"[{component}] {error_message}"
        log_type = 3  # 시스템 오류
        return await self.save_alert(string_id, rsd_id, log_type, description)



# =============================================================================
# 데이터베이스 매니저
# =============================================================================

class DatabaseManager:
    """데이터베이스 매니저 - 모든 저장소를 통합 관리하는 팩토리 클래스"""
    
    def __init__(self, config: DatabaseConfig):
        """
        데이터베이스 매니저 초기화
        
        Args:
            config: 데이터베이스 설정
        """
        self.config = config
        self.connection = DatabaseConnection(config)
        
        # 저장소들 (연결 후에 생성됨)
        self.sensor_repository: Optional[SensorDataRepository] = None
        self.device_repository: Optional[DeviceRepository] = None
        self.alert_repository: Optional[AlertRepository] = None
        
        self._is_initialized = False
    
    async def initialize(self) -> bool:
        """
        데이터베이스 매니저 초기화 및 저장소 생성
        
        Returns:
            초기화 성공 여부
        """
        if self._is_initialized:
            logger.warning("데이터베이스 매니저가 이미 초기화되었습니다")
            return True
            
        # 데이터베이스 연결
        if not await self.connection.connect():
            return False
        
        # 저장소들 생성
        self.sensor_repository = SensorDataRepository(self.connection)
        self.device_repository = DeviceRepository(self.connection)
        self.alert_repository = AlertRepository(self.connection)
        
        self._is_initialized = True
        logger.info("데이터베이스 매니저 초기화 완료")
        return True
    
    async def close(self) -> None:
        """데이터베이스 매니저 종료"""
        if self._is_initialized:
            await self.connection.disconnect()
            self.sensor_repository = None
            self.device_repository = None
            self.alert_repository = None
            self._is_initialized = False
            logger.info("데이터베이스 매니저 종료")

    # =========================================================================
    # 신규 메서드: CSV 백업
    # =========================================================================
    def backup_data_to_csv(self, sensor_data_list: List[RSDSensorData]) -> str:
        """
        저장 실패한 센서 데이터를 CSV 파일로 백업합니다.

        Args:
            sensor_data_list: 백업할 센서 데이터 리스트

        Returns:
            저장된 CSV 파일의 경로. 실패 시 빈 문자열 반환.
        """
        if not sensor_data_list:
            return ""

        backup_dir = "backup_data"
        try:
            os.makedirs(backup_dir, exist_ok=True)
            
            timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
            file_path = os.path.join(backup_dir, f"backup_{timestamp}.csv")

            header = [
                'timestamp', 'string_id', 'rsd_id', 'channel_no', 
                'temperature', 'current', 'is_arc', 'arc_frequency', 
                'arc_count', 'rsd_status'
            ]

            with open(file_path, 'w', newline='', encoding='utf-8') as f:
                writer = csv.writer(f)
                writer.writerow(header)

                for data in sensor_data_list:
                    for channel in data.channels:
                        row = [
                            data.timestamp.strftime("%Y-%m-%d %H:%M:%S.%f"),
                            data.string_id,
                            data.rsd_id,
                            channel.channel_no,
                            channel.temperature,
                            channel.current,
                            channel.is_arc,
                            channel.arc_frequency,
                            channel.arc_count,
                            data.rsd_status
                        ]
                        writer.writerow(row)
            
            logger.info(f"데이터 백업 성공: {len(sensor_data_list)}개 RSD 데이터 -> {file_path}")
            return file_path

        except Exception as e:
            logger.error(f"CSV 백업 실패: {e}")
            return ""

    def get_sensor_repository(self) -> Optional[SensorDataRepository]:
        """센서 데이터 저장소 반환"""
        if not self._is_initialized:
            logger.error("데이터베이스 매니저가 초기화되지 않았습니다")
            return None
        return self.sensor_repository
    
    def get_device_repository(self) -> Optional[DeviceRepository]:
        """장치 정보 저장소 반환"""
        if not self._is_initialized:
            logger.error("데이터베이스 매니저가 초기화되지 않았습니다")
            return None
        return self.device_repository
    
    def get_alert_repository(self) -> Optional[AlertRepository]:
        """알림 저장소 반환"""
        if not self._is_initialized:
            logger.error("데이터베이스 매니저가 초기화되지 않았습니다")
            return None
        return self.alert_repository
    
    def get_connection(self) -> DatabaseConnection:
        """데이터베이스 연결 객체 반환"""
        return self.connection
    
    async def test_connection(self) -> bool:
        """연결 테스트"""
        return await self.connection.test_connection()
    
    def is_initialized(self) -> bool:
        """초기화 상태 확인"""
        return self._is_initialized