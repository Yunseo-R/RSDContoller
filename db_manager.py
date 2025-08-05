"""
RSD 모니터링 시스템 데이터베이스 관리자
PostgreSQL 연결, 기기 목록, 센싱값 데이터, 아크 알림 관리
미완성 메서드들 완성 및 안정성 개선
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

@dataclass
class AlertData:
    """알림 데이터"""
    string_id: Optional[int]
    rsd_id: Optional[int]
    log_type: int
    log_title: str
    log_content: str
    reg_date: datetime
    channel_no: Optional[int] = None


# =============================================================================
# 데이터베이스 연결 클래스
# =============================================================================

class DatabaseConnection:
    """데이터베이스 연결 관리"""
    
    def __init__(self, config: DatabaseConfig, reconnection_callback=None):
        """
        데이터베이스 연결 초기화
        
        Args:
            config: 데이터베이스 설정
            reconnection_callback: 재연결 시 호출될 콜백 함수
        """
        self.config = config
        self._pool: Optional[asyncpg.Pool] = None
        self.is_connected = False
        self._reconnection_callback = reconnection_callback
        self._monitoring_task: Optional[asyncio.Task] = None
    
    async def connect(self) -> bool:
        """데이터베이스 연결"""
        try:
            dsn = f"postgresql://{self.config.username}:{self.config.password}@{self.config.host}:{self.config.port}/{self.config.database}"
            
            self._pool = await asyncpg.create_pool(
                dsn,
                min_size=2,
                max_size=10,
                command_timeout=30
            )
            
            # 연결 테스트
            async with self._pool.acquire() as conn:
                await conn.fetchval("SELECT 1")
            
            self.is_connected = True
            logger.info(f"데이터베이스 연결 성공: {self.config.host}:{self.config.port}")
            
            # 연결 상태 모니터링 시작
            self._start_connection_monitoring()
            
            return True
            
        except Exception as e:
            logger.error(f"데이터베이스 연결 실패: {e}")
            self.is_connected = False
            return False
    
    async def disconnect(self) -> None:
        """데이터베이스 연결 해제"""
        try:
            # 모니터링 태스크 종료
            if self._monitoring_task and not self._monitoring_task.done():
                self._monitoring_task.cancel()
                try:
                    await self._monitoring_task
                except asyncio.CancelledError:
                    pass
            
            if self._pool:
                await self._pool.close()
                self._pool = None
            
            self.is_connected = False
            logger.info("데이터베이스 연결 해제 완료")
            
        except Exception as e:
            logger.error(f"데이터베이스 연결 해제 중 오류: {e}")
    
    def _start_connection_monitoring(self):
        """연결 상태 모니터링 시작"""
        if self._monitoring_task and not self._monitoring_task.done():
            return
        
        self._monitoring_task = asyncio.create_task(self._monitor_connection())
    
    async def _monitor_connection(self):
        """연결 상태 모니터링"""
        last_status = True
        
        while True:
            try:
                await asyncio.sleep(10)  # 10초마다 확인
                
                current_status = await self.test_connection()
                
                if current_status != last_status:
                    self.is_connected = current_status
                    if current_status:
                        logger.info("데이터베이스 연결이 복구되었습니다")
                        if self._reconnection_callback:
                            logger.info("재연결 콜백을 호출합니다")
                            asyncio.create_task(self._reconnection_callback())
                    else:
                        logger.warning("데이터베이스 연결이 끊어졌습니다")
                    
                    last_status = current_status
                    
            except asyncio.CancelledError:
                logger.info("연결 모니터링이 종료되었습니다")
                break
            except Exception as e:
                logger.error(f"연결 상태 확인 중 오류: {e}")

    async def test_connection(self) -> bool:
        """연결 테스트"""
        try:
            if not self._pool:
                return False
                
            async with self._pool.acquire() as conn:
                result = await conn.fetchval("SELECT 1")
                return result == 1
                
        except Exception as e:
            logger.debug(f"연결 테스트 실패: {e}")
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
            if not self._pool:
                raise ConnectionError("데이터베이스 풀이 초기화되지 않았습니다")
            
            async with self._pool.acquire() as conn:
                result = await conn.execute(query, *args)
                return result
                
        except (OSError, asyncpg.exceptions.ConnectionDoesNotExistError, ConnectionError) as e:
            self.is_connected = False
            logger.error(f"명령 실행 실패 (연결 오류): {e}")
            raise
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
            if not self._pool:
                raise ConnectionError("데이터베이스 풀이 초기화되지 않았습니다")
                
            async with self._pool.acquire() as conn:
                await conn.executemany(query, args_list)

        except (OSError, asyncpg.exceptions.ConnectionDoesNotExistError, ConnectionError) as e:
            self.is_connected = False
            logger.error(f"배치 명령 실행 실패 (연결 오류): {e}")
            raise
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
            저장 결과 딕셔너리 (success_count, error_count, total_count)
        """
        if not sensor_data_list:
            return {
                'success_count': 0,
                'error_count': 0,
                'total_count': 0
            }
        
        success_count = 0
        error_count = 0
        total_count = len(sensor_data_list)
        
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
        
        try:
            insert_query = """
            INSERT INTO TB_RSD_DATA3 (
                string_id, rsd_id, channel_no, rsd_status, 
                temperature, current, is_arc, arc_frequency, arc_count,
                arc_date, recv_time
            ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11)
            """
            
            await self.connection.execute_many(insert_query, batch_data)
            success_count = total_count
            
        except Exception as e:
            logger.error(f"센서 데이터 배치 저장 실패: {e}")
            error_count = total_count
            raise  # 호출자가 백업 처리할 수 있도록 예외 전파
        
        return {
            'success_count': success_count,
            'error_count': error_count,
            'total_count': total_count
        }

    def backup_data_to_csv(self, sensor_data_list: List[RSDSensorData]) -> str:
        """
        센서 데이터를 CSV 파일로 백업
        
        Args:
            sensor_data_list: 백업할 센서 데이터 리스트

        Returns:
            저장된 CSV 파일의 경로. 실패 시 빈 문자열 반환.
        """
        if not sensor_data_list:
            return ""

        backup_dir = "backup"
        try:
            os.makedirs(backup_dir, exist_ok=True)

            date_str = datetime.now().strftime("%y%m%d")
            file_path = os.path.join(backup_dir, f"backup_data_{date_str}.csv")

            write_header = not os.path.exists(file_path)
            open_mode = 'a' if not write_header else 'w'

            header = [
                'timestamp', 'string_id', 'rsd_id', 'channel_no',
                'temperature', 'current', 'is_arc', 'arc_frequency',
                'arc_count', 'rsd_status'
            ]

            with open(file_path, open_mode, newline='', encoding='utf-8') as f:
                writer = csv.writer(f)
                if write_header:
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

            log_action = "생성" if write_header else "추가"
            logger.info(f"데이터 백업 {log_action} 성공: {len(sensor_data_list)}개 RSD 데이터 -> {file_path}")
            return file_path

        except Exception as e:
            logger.error(f"CSV 백업 실패: {e}")
            return ""

    def _parse_csv_to_sensor_data(self, file_path: str) -> List[RSDSensorData]:
        """
        CSV 파일을 파싱하여 RSDSensorData 리스트로 변환
        동일한 타임스탬프, string_id, rsd_id를 가진 row들을 하나의 RSDSensorData로 그룹화
        """
        grouped_data = {}
        try:
            with open(file_path, 'r', newline='', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    key = (row['timestamp'], int(row['string_id']), int(row['rsd_id']))

                    if key not in grouped_data:
                        grouped_data[key] = {
                            'string_id': int(row['string_id']),
                            'rsd_id': int(row['rsd_id']),
                            'rsd_status': int(row['rsd_status']),
                            'timestamp': datetime.strptime(row['timestamp'], "%Y-%m-%d %H:%M:%S.%f"),
                            'channels': []
                        }

                    grouped_data[key]['channels'].append(ChannelData(
                        channel_no=int(row['channel_no']),
                        temperature=float(row['temperature']),
                        current=float(row['current']),
                        is_arc=(row['is_arc'].lower() == 'true'),
                        arc_frequency=int(row['arc_frequency']),
                        arc_count=int(row['arc_count'])
                    ))

            sensor_data_list = [
                RSDSensorData(**data) for data in grouped_data.values()
            ]
            return sensor_data_list

        except Exception as e:
            logger.error(f"CSV 파일 파싱 실패 ({os.path.basename(file_path)}): {e}")
            return []

    async def process_pending_backups(self) -> Dict[str, int]:
        """
        백업 디렉터리의 모든 데이터 CSV 파일을 DB로 복구
        """
        backup_dir = "backup"
        if not os.path.exists(backup_dir):
            return {'processed': 0, 'success': 0, 'failed': 0}

        csv_files = [f for f in os.listdir(backup_dir) if f.startswith('backup_data_') and f.endswith('.csv')]
        if not csv_files:
            return {'processed': 0, 'success': 0, 'failed': 0}

        total_files = len(csv_files)
        success_count = 0
        failed_count = 0

        logger.info(f"데이터 백업 파일 {total_files}개 발견. DB 복구를 시작합니다")

        for file_name in csv_files:
            file_path = os.path.join(backup_dir, file_name)
            logger.info(f"파일 처리 중: {file_name}")

            sensor_data_to_save = self._parse_csv_to_sensor_data(file_path)
            if not sensor_data_to_save:
                logger.warning(f"{file_name} 파싱 결과 데이터가 없어 건너뜁니다")
                failed_count += 1
                continue

            is_saved = False
            for attempt in range(1, 3):
                try:
                    logger.info(f"DB 저장 시도 #{attempt} (대상: {file_name})")
                    result = await self.save_sensor_data_batch(sensor_data_to_save)

                    if result.get('success_count', 0) > 0:
                        logger.info(f"파일 DB 저장 성공: {file_name}")
                        is_saved = True
                        break
                    else:
                        logger.warning(f"DB 저장 시도 #{attempt} 실패: 저장된 데이터 0개 ({file_name})")

                except Exception as e:
                    logger.error(f"DB 저장 시도 #{attempt} 중 예외 ({file_name}): {e}")

                await asyncio.sleep(1)

            if is_saved:
                try:
                    os.remove(file_path)
                    logger.info(f"백업 파일 삭제 완료: {file_name}")
                    success_count += 1
                except OSError as e:
                    logger.error(f"백업 파일 삭제 실패 ({file_name}): {e}")
                    failed_count += 1
            else:
                logger.error(f"최종 DB 저장 실패: 백업 파일 유지 ({file_name})")
                failed_count += 1

        return {'processed': total_files, 'success': success_count, 'failed': failed_count}


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
            logger.error(f"활성 String 목록 조회 실패: {e}")
            return []
    
    async def get_active_devices_by_string(self, string_id: int) -> List[DeviceInfo]:
        """
        특정 String의 활성 RSD 목록 조회
        
        Args:
            string_id: String ID
            
        Returns:
            RSD 장치 정보 리스트
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
            logger.error(f"String {string_id}의 활성 RSD 목록 조회 실패: {e}")
            return []
    
    async def get_all_active_devices(self) -> List[DeviceInfo]:
        """
        모든 활성 RSD 목록 조회
        
        Returns:
            모든 RSD 장치 정보 리스트
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
    
    async def _attempt_save_alert(self, alert: AlertData) -> None:
        """
        실제 DB에 알림 저장을 시도하는 내부 메서드
        실패 시 예외를 발생시킵니다
        """
        insert_query = """
        INSERT INTO TB_ALERT_LOG3 (
            string_id, rsd_id, log_type, log_title, log_content, reg_date
        ) VALUES ($1, $2, $3, $4, $5, $6)
        """
        await self.connection.execute_command(
            insert_query,
            alert.string_id,
            alert.rsd_id,
            alert.log_type,
            alert.log_title,
            alert.log_content,
            alert.reg_date
        )

    def _is_valid_device_alert(self, string_id: Optional[int], rsd_id: Optional[int]) -> bool:
        """
        특정 기기와 관련된 유효한 알림인지 확인
        
        Args:
            string_id: String ID
            rsd_id: RSD ID
            
        Returns:
            유효한 기기 알림 여부
        """
        if string_id is None or rsd_id is None:
            return False
        if string_id == 0 or rsd_id == 0:
            return False
        if string_id <= 0 or rsd_id <= 0:
            return False
        
        return True

    async def save_alert(self, string_id: Optional[int], rsd_id: Optional[int], log_type: int,
                     description: str, channel_no: Optional[int] = None,
                     event_time: Optional[datetime] = None) -> bool:
        """
        알림 저장 (특정 기기와 관련되지 않은 알림은 DB 저장하지 않음)
        
        Args:
            string_id: String ID
            rsd_id: RSD ID
            log_type: 알림 타입 (1: 아크 발생, 2: 통신 오류, 3: 시스템 오류)
            description: 알림 설명
            channel_no: 채널 번호 (선택사항)
            event_time: 이벤트 발생 시간 (None이면 현재 시간 사용)
            
        Returns:
            저장 성공 여부 (유효하지 않은 알림은 항상 True 반환)
        """
        # 특정 기기와 관련되지 않은 알림은 DB에 저장하지 않음
        if not self._is_valid_device_alert(string_id, rsd_id):
            logger.info(f"시스템 알림 (DB 저장 제외): String {string_id}, RSD {rsd_id}: {description}")
            return True

        if channel_no is not None:
            log_title = f"채널 {channel_no} 알림"
        else:
            log_title = "기기 알림"

        alert_data = AlertData(
            string_id=string_id,
            rsd_id=rsd_id,
            log_type=log_type,
            log_title=log_title,
            log_content=description,
            reg_date=event_time if event_time is not None else datetime.now(),
            channel_no=channel_no
        )

        # DB 연결이 끊어진 상태면 처음부터 백업으로 처리
        if not self.connection.is_connected:
            try:
                file_path = self.backup_alerts_to_csv([alert_data])
                if file_path:
                    logger.info(f"알림 백업 저장 성공 -> {file_path}")
                    return True
                else:
                    logger.error("알림 백업 저장 실패")
                    return False
            except Exception as e:
                logger.error(f"알림 백업 중 예외 발생: {e}")
                return False

        # DB 연결이 있을 때만 DB 저장 시도
        try:
            await self._attempt_save_alert(alert_data)
            logger.info(f"알림 저장 완료 - String {string_id}, RSD {rsd_id}: {description}")
            return True
        except Exception as e:
            logger.warning(f"알림 DB 저장 실패, 백업 처리: {e}")
            try:
                file_path = self.backup_alerts_to_csv([alert_data])
                if file_path:
                    logger.info(f"알림 백업 저장 성공 -> {file_path}")
                    return True
                else:
                    logger.error("치명적 오류: 알림 백업마저 실패했습니다")
                    return False
            except Exception as backup_e:
                logger.error(f"알림 백업 중 예외 발생: {backup_e}")
                return False

    async def save_arc_alert(self, string_id: int, rsd_id: int, channel_no: int, 
                        arc_frequency: int, arc_count: int,
                        event_time: Optional[datetime] = None) -> bool:
        """
        아크 발생 알림 저장
        
        Args:
            string_id: String ID
            rsd_id: RSD ID
            channel_no: 채널 번호
            arc_frequency: 아크 주파수 (KHz)
            arc_count: 감지 횟수
            event_time: 이벤트 발생 시간
            
        Returns:
            저장 성공 여부
        """
        description = f"아크 발생 감지 - CH{channel_no} ({arc_frequency} KHz / {arc_count}회)"
        return await self.save_alert(string_id, rsd_id, 1, description, channel_no, event_time=event_time)

    async def save_communication_error_alert(self, string_id: int, rsd_id: int, 
                                        error_message: str,
                                        event_time: Optional[datetime] = None) -> bool:
        """
        통신 오류 알림 저장
        
        Args:
            string_id: String ID
            rsd_id: RSD ID
            error_message: 오류 메시지
            event_time: 이벤트 발생 시간
            
        Returns:
            저장 성공 여부
        """
        description = f"통신 오류: {error_message}"
        return await self.save_alert(string_id, rsd_id, 2, description, event_time=event_time)
    
    async def save_system_error_alert(self, component: str, error_message: str,
                                string_id: Optional[int] = None,
                                rsd_id: Optional[int] = None,
                                event_time: Optional[datetime] = None) -> bool:
        """
        시스템 오류 알림 저장 (특정 기기와 관련되지 않은 경우 DB 저장하지 않음)
        
        Args:
            component: 컴포넌트 이름
            error_message: 오류 메시지
            string_id: String ID (선택사항)
            rsd_id: RSD ID (선택사항)
            event_time: 이벤트 발생 시간
            
        Returns:
            저장 성공 여부
        """
        description = f"[{component}] {error_message}"
        log_type = 3
        
        return await self.save_alert(string_id, rsd_id, log_type, description, event_time=event_time)
        
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

    def backup_alerts_to_csv(self, alerts_to_backup: List[AlertData]) -> str:
        """
        알림 데이터를 CSV 파일로 백업
        
        Args:
            alerts_to_backup: 백업할 알림 데이터 리스트

        Returns:
            저장된 CSV 파일의 경로. 실패 시 빈 문자열 반환.
        """
        if not alerts_to_backup:
            return ""

        backup_dir = "backup"
        try:
            os.makedirs(backup_dir, exist_ok=True)

            date_str = datetime.now().strftime("%y%m%d")
            file_path = os.path.join(backup_dir, f"backup_log_{date_str}.csv")

            write_header = not os.path.exists(file_path)
            open_mode = 'a' if not write_header else 'w'

            header = [
                'reg_date', 'string_id', 'rsd_id', 'log_type', 'log_title',
                'log_content', 'channel_no'
            ]

            with open(file_path, open_mode, newline='', encoding='utf-8') as f:
                writer = csv.writer(f)
                if write_header:
                    writer.writerow(header)

                for alert in alerts_to_backup:
                    row = [
                        alert.reg_date.strftime("%Y-%m-%d %H:%M:%S.%f"),
                        alert.string_id if alert.string_id is not None else '',
                        alert.rsd_id if alert.rsd_id is not None else '',
                        alert.log_type,
                        alert.log_title,
                        alert.log_content,
                        alert.channel_no if alert.channel_no is not None else ''
                    ]
                    writer.writerow(row)

            log_action = "생성" if write_header else "추가"
            logger.info(f"로그 데이터 백업 {log_action} 성공: {len(alerts_to_backup)}개 알림 -> {file_path}")
            return file_path

        except Exception as e:
            logger.error(f"로그 CSV 백업 실패: {e}")
            return ""

    def _parse_csv_to_alert_data(self, file_path: str) -> List[AlertData]:
        """
        로그 CSV 파일을 파싱하여 AlertData 리스트로 변환
        유효하지 않은 기기 정보가 있는 알림은 제외
        """
        try:
            alerts = []
            with open(file_path, 'r', newline='', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    try:
                        string_id = int(row['string_id']) if row['string_id'] and row['string_id'].strip() else None
                        rsd_id = int(row['rsd_id']) if row['rsd_id'] and row['rsd_id'].strip() else None
                        
                        # 유효하지 않은 기기 정보인 경우 건너뛰기
                        if not self._is_valid_device_alert(string_id, rsd_id):
                            logger.debug(f"유효하지 않은 기기 정보로 백업 복원에서 제외: String {string_id}, RSD {rsd_id}")
                            continue
                        
                        log_type = int(row['log_type'])
                        log_title = row['log_title']
                        log_content = row['log_content']
                        reg_date = datetime.strptime(row['reg_date'], "%Y-%m-%d %H:%M:%S.%f")
                        
                        channel_no = int(row['channel_no']) if row['channel_no'] and row['channel_no'].strip() else None
                        
                        alerts.append(AlertData(
                            string_id=string_id,
                            rsd_id=rsd_id,
                            log_type=log_type,
                            log_title=log_title,
                            log_content=log_content,
                            reg_date=reg_date,
                            channel_no=channel_no
                        ))
                        
                    except (ValueError, KeyError) as e:
                        logger.warning(f"CSV 행 파싱 실패, 건너뜀: {e}")
                        continue

            return alerts

        except Exception as e:
            logger.error(f"CSV 파일 파싱 실패 ({file_path}): {e}")
            return []

    async def restore_alerts_from_csv_backups(self) -> Dict[str, int]:
        """
        백업된 로그 CSV 파일들을 DB로 복구
        유효하지 않은 기기 정보가 있는 알림은 자동으로 제외
        """
        backup_dir = "backup"
        
        if not os.path.exists(backup_dir):
            return {'processed': 0, 'success': 0, 'failed': 0}

        csv_files = [f for f in os.listdir(backup_dir) if f.startswith("backup_log_") and f.endswith(".csv")]
        
        if not csv_files:
            return {'processed': 0, 'success': 0, 'failed': 0}

        total_files = len(csv_files)
        success_count = 0
        failed_count = 0

        logger.info(f"로그 백업 파일 {total_files}개 발견. DB 복구를 시작합니다")

        for file_name in csv_files:
            file_path = os.path.join(backup_dir, file_name)
            logger.info(f"로그 파일 처리 중: {file_name}")

            alerts_to_save = self._parse_csv_to_alert_data(file_path)
            if not alerts_to_save:
                logger.warning(f"{file_name} 파싱 결과 유효한 데이터가 없어 건너뜁니다")
                failed_count += 1
                continue

            all_saved = True
            try:
                alert_tuples = [
                    (a.string_id, a.rsd_id, a.log_type, a.log_title, a.log_content, a.reg_date)
                    for a in alerts_to_save
                ]
                query = """
                INSERT INTO TB_ALERT_LOG3 (
                    string_id, rsd_id, log_type, log_title, log_content, reg_date
                ) VALUES ($1, $2, $3, $4, $5, $6)
                """
                await self.connection.execute_many(query, alert_tuples)
                logger.info(f"백업된 로그 {len(alerts_to_save)}개 DB 저장 완료: {file_name}")
            except Exception as e:
                logger.error(f"백업된 로그 배치 저장 실패 (파일: {file_name}): {e}")
                all_saved = False

            if all_saved:
                try:
                    os.remove(file_path)
                    logger.info(f"로그 백업 파일 삭제 완료: {file_name}")
                    success_count += 1
                except OSError as e:
                    logger.error(f"로그 백업 파일 삭제 실패 ({file_name}): {e}")
                    failed_count += 1
            else:
                logger.error(f"로그 DB 저장 실패: 백업 파일 유지 ({file_name})")
                failed_count += 1

        return {'processed': total_files, 'success': success_count, 'failed': failed_count}


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
        self._status_callback: Optional[callable] = None
        # 내부 핸들러를 DatabaseConnection에 전달
        self.connection = DatabaseConnection(config, self._handle_reconnection)
        
        # 저장소들 (연결 후에 생성됨)
        self.sensor_repository: Optional[SensorDataRepository] = None
        self.device_repository: Optional[DeviceRepository] = None
        self.alert_repository: Optional[AlertRepository] = None
        
        self._is_initialized = False
        self._backup_processing_lock = asyncio.Lock()
        self._db_was_disconnected = False

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

    def set_disconnection_flag(self, status: bool):
        """DB 연결 끊김 상태 플래그를 설정합니다"""
        if status and not self._db_was_disconnected:
            logger.warning("DB 연결이 끊어진 것으로 감지되었습니다. 이후 DB 쓰기 실패 시 데이터는 백업됩니다")
        self._db_was_disconnected = status

    def get_disconnection_flag(self) -> bool:
        """DB 연결 끊김 상태를 반환합니다"""
        return self._db_was_disconnected

    async def close(self) -> None:
        """데이터베이스 매니저 종료"""
        if self._is_initialized:
            await self.connection.disconnect()
            self.sensor_repository = None
            self.device_repository = None
            self.alert_repository = None
            self._is_initialized = False
            logger.info("데이터베이스 매니저 종료")

    def set_status_callback(self, callback: callable):
        """
        DB 재연결 시 실행될 콜백 함수를 등록합니다
        
        Args:
            callback: 재연결 시 실행할 비동기 콜백 함수
        """
        self._status_callback = callback
        logger.info("DB 재연결 콜백 함수가 등록되었습니다")

    async def _handle_reconnection(self):
        """
        DatabaseConnection으로부터 재연결 신호를 받았을 때 처리하는 내부 메서드
        등록된 외부 콜백을 호출합니다
        """
        if self._status_callback:
            # 등록된 외부 콜백이 있으면 비동기적으로 실행
            asyncio.create_task(self._status_callback())

    async def process_pending_log_backups(self) -> Dict[str, int]:
        """
        백업된 로그 파일 처리 (AlertRepository로 위임)
        
        Returns:
            처리 결과
        """
        if not self.alert_repository:
            logger.error("AlertRepository가 초기화되지 않았습니다")
            return {'processed': 0, 'success': 0, 'failed': 0}
        
        return await self.alert_repository.restore_alerts_from_csv_backups()

    async def process_pending_data_backups(self) -> Dict[str, int]:
        """
        백업된 센서 데이터 파일 처리 (SensorDataRepository로 위임)
        
        Returns:
            처리 결과
        """
        if not self.sensor_repository:
            logger.error("SensorDataRepository가 초기화되지 않았습니다")
            return {'processed': 0, 'success': 0, 'failed': 0}
        
        return await self.sensor_repository.process_pending_backups()
    
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