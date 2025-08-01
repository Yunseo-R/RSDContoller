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
    """데이터베이스 연결 관리자"""
    
    def __init__(self, config: DatabaseConfig, db_reconnected_event: asyncio.Event):
        """
        데이터베이스 연결 초기화
        
        Args:
            config: 데이터베이스 설정
            db_reconnected_event: DB 재연결 시그널링을 위한 asyncio.Event
        """
        self.config = config
        self._pool: Optional[asyncpg.Pool] = None
        self.is_connected = False
        self._db_reconnected_event = db_reconnected_event
        self._db_was_disconnected = False
     

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
        INSERT/UPDATE/DELETE 쿼리 실행 (연결 상태 감지 로직 추가)
        
        Args:
            query: SQL 쿼리
            *args: 쿼리 파라미터
            
        Returns:
            실행 결과 상태
        """
        try:
            if not self._pool:
                raise ConnectionError("데이터베이스 풀이 초기화되지 않았습니다.")
            
            async with self._pool.acquire() as conn:
                result = await conn.execute(query, *args)
                # 쓰기 성공 시, '연결 끊김' 상태였다면 복구 신호 전송
                if self._db_was_disconnected:
                    self._db_reconnected_event.set()
                    self._db_was_disconnected = False # 플래그 리셋
                return result
                
        except (OSError, asyncpg.exceptions.ConnectionDoesNotExistError, ConnectionError) as e:
            # 연결 오류 발생 시 '연결 끊김' 플래그 설정
            self._db_was_disconnected = True
            logger.error(f"명령 실행 실패 (연결 오류 감지): {e}")
            raise
        except Exception as e:
            logger.error(f"명령 실행 실패: {e}")
            raise
    
    async def execute_many(self, query: str, args_list: List[tuple]) -> None:
        """
        배치 명령 실행 (연결 상태 감지 로직 추가)
        
        Args:
            query: SQL 쿼리
            args_list: 파라미터 리스트
        """
        try:
            if not self._pool:
                raise ConnectionError("데이터베이스 풀이 초기화되지 않았습니다.")

            async with self._pool.acquire() as conn:
                await conn.executemany(query, args_list)
                # 배치 쓰기 성공 시, '연결 끊김' 상태였다면 복구 신호 전송
                if self._db_was_disconnected:
                    self._db_reconnected_event.set()
                    self._db_was_disconnected = False # 플래그 리셋

        except (OSError, asyncpg.exceptions.ConnectionDoesNotExistError, ConnectionError) as e:
            # 연결 오류 발생 시 '연결 끊김' 플래그 설정
            self._db_was_disconnected = True
            logger.error(f"배치 명령 실행 실패 (연결 오류 감지): {e}")
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
            # 실패 시 CSV 백업 로직 호출
            self.backup_data_to_csv(sensor_data_list)
            return {
                'total_count': len(sensor_data_list),
                'success_count': 0,
                'error_count': len(sensor_data_list)
            }

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

    def _parse_csv_to_sensor_data(self, file_path: str) -> List[RSDSensorData]:
        """
        단일 CSV 파일을 파싱하여 RSDSensorData 리스트로 변환합니다.
        동일한 타임스탬프, string_id, rsd_id를 가진 row들을 하나의 RSDSensorData로 그룹화합니다.
        """
        grouped_data = {}
        try:
            with open(file_path, 'r', newline='', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    # 그룹화를 위한 복합 키 생성
                    key = (row['timestamp'], int(row['string_id']), int(row['rsd_id']))

                    if key not in grouped_data:
                        grouped_data[key] = {
                            'string_id': int(row['string_id']),
                            'rsd_id': int(row['rsd_id']),
                            'rsd_status': int(row['rsd_status']),
                            'timestamp': datetime.strptime(row['timestamp'], "%Y-%m-%d %H:%M:%S.%f"),
                            'channels': []
                        }

                    # 채널 데이터 추가
                    grouped_data[key]['channels'].append(ChannelData(
                        channel_no=int(row['channel_no']),
                        temperature=float(row['temperature']),
                        current=float(row['current']),
                        is_arc=(row['is_arc'].lower() == 'true'),
                        arc_frequency=int(row['arc_frequency']),
                        arc_count=int(row['arc_count'])
                    ))

            # 그룹화된 데이터를 RSDSensorData 객체 리스트로 변환
            sensor_data_list = [
                RSDSensorData(**data) for data in grouped_data.values()
            ]
            return sensor_data_list

        except Exception as e:
            logger.error(f"CSV 파일 파싱 실패 ({os.path.basename(file_path)}): {e}")
            return []

    async def process_pending_backups(self) -> Dict[str, Any]:
        """
        'backup_data' 디렉터리의 모든 CSV 파일을 처리하여 DB에 저장합니다.
        성공 시 CSV 파일을 삭제하고, 실패 시 그대로 둡니다.
        """
        backup_dir = "backup_data"
        if not os.path.exists(backup_dir):
            return {'processed': 0, 'success': 0, 'failed': 0}

        csv_files = [f for f in os.listdir(backup_dir) if f.endswith('.csv')]
        if not csv_files:
            return {'processed': 0, 'success': 0, 'failed': 0}

        total_files = len(csv_files)
        success_count = 0
        failed_count = 0

        logger.info(f"DB에 저장되지 않은 백업 파일 {total_files}개를 발견했습니다. 복구를 시작합니다.")

        for file_name in csv_files:
            file_path = os.path.join(backup_dir, file_name)
            logger.info(f"파일 처리 중: {file_name}")

            # 1. CSV 파일 파싱
            sensor_data_to_save = self._parse_csv_to_sensor_data(file_path)
            if not sensor_data_to_save:
                logger.warning(f"{file_name} 파싱 결과 데이터가 없어 건너뜁니다.")
                failed_count += 1
                continue

            # 2. DB 저장 시도 (최대 2회)
            is_saved = False
            for attempt in range(1, 3): # 1차 시도, 2차 재시도
                try:
                    logger.info(f"DB 저장 시도 #{attempt} (대상: {file_name})")
                    result = await self.save_sensor_data_batch(sensor_data_to_save)

                    if result.get('success_count', 0) > 0:
                        logger.info(f"파일 DB 저장 성공: {file_name}")
                        is_saved = True
                        break # 저장 성공 시 재시도 루프 탈출
                    else:
                        logger.warning(f"DB 저장 시도 #{attempt} 실패: 저장된 데이터 0개 ({file_name})")

                except Exception as e:
                    logger.error(f"DB 저장 시도 #{attempt} 중 예외 발생 ({file_name}): {e}")

                await asyncio.sleep(1) # 재시도 전 1초 대기

            # 3. 결과에 따른 파일 처리
            if is_saved:
                try:
                    os.remove(file_path)
                    logger.info(f"백업 파일 삭제 완료: {file_name}")
                    success_count += 1
                except OSError as e:
                    logger.error(f"백업 파일 삭제 실패 ({file_name}): {e}")
                    failed_count += 1 # 파일 삭제에 실패했으므로 실패로 간주
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
        self._current_log_backup_path: Optional[str] = None
    
    async def _attempt_save_alert(self, alert: AlertData) -> None:
        """
        실제 DB에 알림 저장을 시도하는 내부 메서드. 실패 시 예외를 발생시킵니다.
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

    async def save_alert(self, string_id: Optional[int], rsd_id: Optional[int], log_type: int,
                    description: str, channel_no: Optional[int] = None,
                    event_time: Optional[datetime] = None) -> bool:
        """
        알림 저장 (재시도, 백업, 시간 지정 로직 추가)
        
        Args:
            string_id: String ID
            rsd_id: RSD ID
            log_type: 알림 타입 (1: 아크 발생, 2: 통신 오류, 3: 시스템 오류)
            description: 알림 설명
            channel_no: 채널 번호 (선택사항)
            event_time: 이벤트 발생 시간 (None이면 현재 시간 사용)
            
        Returns:
            저장 성공 여부 (DB 저장 또는 백업 성공 시 True)
        """
        if channel_no is not None:
            log_title = f"채널 {channel_no} 알림"
        else:
            log_title = "시스템 알림"

        alert_data = AlertData(
            string_id=string_id,
            rsd_id=rsd_id,
            log_type=log_type,
            log_title=log_title,
            log_content=description,
            reg_date=event_time if event_time is not None else datetime.now(),
            channel_no=channel_no
        )

        # 1. 1차 저장 시도
        try:
            await self._attempt_save_alert(alert_data)
            logger.info(f"알림 저장 완료 - String {string_id}, RSD {rsd_id}: {description}")
            return True
        except Exception as e:
            logger.warning(f"알림 저장 1차 실패, 재시도합니다. 오류: {e}")

        # 2. 재시도 (1회)
        await asyncio.sleep(0.5)
        try:
            await self._attempt_save_alert(alert_data)
            logger.info(f"알림 저장 재시도 성공 - String {string_id}, RSD {rsd_id}: {description}")
            return True
        except Exception as e:
            logger.error(f"알림 저장 재시도 실패. CSV 백업을 시도합니다. 오류: {e}")
        
        # 3. CSV 백업
        try:
            # 자체 백업 함수를 사용하도록 수정
            file_path = self.backup_alerts_to_csv([alert_data])
            if file_path:
                logger.info(f"알림 데이터 백업 성공 -> {file_path}")
                return True
            else:
                logger.error("치명적 오류: 알림 데이터 CSV 백업마저 실패했습니다.")
                return False
        except Exception as e:
            logger.error(f"알림 데이터 CSV 백업 중 예외 발생: {e}")
            return False
    
    async def save_arc_alert(self, string_id: int, rsd_id: int, channel_no: int, 
                        arc_frequency: int, arc_count: int,
                        event_time: Optional[datetime] = None) -> bool:
        """
        아크 발생 알림 저장 (이벤트 시간 전달 기능 추가)
        
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
                                        error_message: str,
                                        event_time: Optional[datetime] = None) -> bool:
        """
        통신 오류 알림 저장 (이벤트 시간 전달 기능 추가)
        
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
        시스템 오류 알림 저장 (이벤트 시간 전달 기능 추가)
        
        Args:
            component: 오류 발생 컴포넌트
            error_message: 오류 메시지
            string_id: String ID (선택사항)
            rsd_id: RSD ID (선택사항)
            event_time: 이벤트 발생 시간
            
        Returns:
            저장 성공 여부
        """
        description = f"[{component}] {error_message}"
        log_type = 3  # 시스템 오류
        return await self.save_alert(string_id, rsd_id, log_type, description, event_time=event_time)

    def backup_alerts_to_csv(self, alerts_to_backup: List[AlertData]) -> str:
        """
        저장 실패한 알림 데이터를 CSV 파일로 백업
        한 세션에서는 하나의 파일에 계속 추가

        Args:
            alerts_to_backup: 백업할 알림 데이터 리스트

        Returns:
            저장된 CSV 파일의 경로. 실패 시 빈 문자열 반환.
        """
        if not alerts_to_backup:
            return ""

        backup_dir = "backup_logs"
        try:
            os.makedirs(backup_dir, exist_ok=True)

            # 현재 세션에서 사용 중인 백업 파일이 있는지 확인
            if self._current_log_backup_path and os.path.exists(self._current_log_backup_path):
                file_path = self._current_log_backup_path
                write_header = False
                open_mode = 'a'
            else:
                # 새 세션 또는 첫 백업 시 새 파일 생성
                timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
                file_path = os.path.join(backup_dir, f"backup_log_{timestamp}.csv")
                self._current_log_backup_path = file_path # 현재 세션 파일 경로 저장
                write_header = True
                open_mode = 'w'

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

            log_action = "추가" if open_mode == 'a' else "생성"
            logger.info(f"로그 데이터 백업 {log_action} 성공: {len(alerts_to_backup)}개 알림 -> {file_path}")
            return file_path

        except Exception as e:
            logger.error(f"로그 CSV 백업 실패: {e}")
            return ""

    def _parse_csv_to_alert_data(self, file_path: str) -> List[AlertData]:
        """
        단일 로그 CSV 파일을 파싱하여 AlertData 리스트로 변환합니다.
        """
        alerts = []
        try:
            with open(file_path, 'r', newline='', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    alerts.append(AlertData(
                        reg_date=datetime.strptime(row['reg_date'], "%Y-%m-%d %H:%M:%S.%f"),
                        string_id=int(row['string_id']) if row['string_id'] else None,
                        rsd_id=int(row['rsd_id']) if row['rsd_id'] else None,
                        log_type=int(row['log_type']),
                        log_title=row['log_title'],
                        log_content=row['log_content'],
                        channel_no=int(row['channel_no']) if row['channel_no'] else None
                    ))
            return alerts
        except Exception as e:
            logger.error(f"로그 CSV 파일 파싱 실패 ({os.path.basename(file_path)}): {e}")
            return []

    async def process_pending_log_backups(self) -> Dict[str, Any]:
        """
        'backup_logs' 디렉터리의 모든 CSV 파일을 처리하여 DB에 저장합니다.
        성공 시 CSV 파일을 삭제하고, 실패 시 그대로 둡니다.
        """
        backup_dir = "backup_logs"
        if not os.path.exists(backup_dir):
            return {'processed': 0, 'success': 0, 'failed': 0}

        csv_files = [f for f in os.listdir(backup_dir) if f.endswith('.csv')]
        if not csv_files:
            return {'processed': 0, 'success': 0, 'failed': 0}

        total_files = len(csv_files)
        success_count = 0
        failed_count = 0

        logger.info(f"DB에 저장되지 않은 로그 백업 파일 {total_files}개를 발견했습니다. 복구를 시작합니다.")

        for file_name in csv_files:
            file_path = os.path.join(backup_dir, file_name)
            logger.info(f"로그 파일 처리 중: {file_name}")

            alerts_to_save = self._parse_csv_to_alert_data(file_path)
            if not alerts_to_save:
                logger.warning(f"{file_name} 파싱 결과 데이터가 없어 건너뜁니다.")
                failed_count += 1
                continue

            all_saved = True
            try:
                # 배치로 한 번에 저장 시도
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
            except Exception as e:
                logger.error(f"백업된 로그 배치 저장 실패 (파일: {file_name}): {e}")
                all_saved = False

            if all_saved:
                try:
                    os.remove(file_path)
                    logger.info(f"로그 백업 파일 삭제 완료: {file_name}")
                    success_count += 1
                    # 현재 세션 파일이 삭제된 경우, 경로 초기화
                    if file_path == self._current_log_backup_path:
                        self._current_log_backup_path = None
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
        self._db_reconnected_event = asyncio.Event()
        self.connection = DatabaseConnection(config, self._db_reconnected_event)
        
        # 저장소들 (연결 후에 생성됨)
        self.sensor_repository: Optional[SensorDataRepository] = None
        self.device_repository: Optional[DeviceRepository] = None
        self.alert_repository: Optional[AlertRepository] = None
        
        self._is_initialized = False
        self._current_log_backup_path: Optional[str] = None
        self._backup_processing_lock = asyncio.Lock()
        self._backup_task: Optional[asyncio.Task] = None 
    
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
            self.connection._db_was_disconnected = True # 초기 연결 실패 시 플래그 설정
            return False

        # 저장소들 생성 (AlertRepository 생성 시 backup_function 인자 제거)
        self.sensor_repository = SensorDataRepository(self.connection)
        self.device_repository = DeviceRepository(self.connection)
        self.alert_repository = AlertRepository(self.connection)
        
        # 백업 처리 백그라운드 태스크 시작
        self._backup_task = asyncio.create_task(self._backup_processing_task())

        self._is_initialized = True
        logger.info("데이터베이스 매니저 초기화 완료")
        return True

    def set_disconnection_flag(self, status: bool):
        """DB 연결 끊김 상태 플래그를 설정합니다."""
        if status and not self._db_was_disconnected:
            logger.warning("DB 연결이 끊어진 것으로 감지되었습니다. 이후 DB 쓰기 실패 시 데이터는 백업됩니다.")
        self._db_was_disconnected = status

    def get_disconnection_flag(self) -> bool:
        """DB 연결 끊김 상태를 반환합니다."""
        return self._db_was_disconnected

    async def _backup_processing_task(self):
        """
        DB 재연결 이벤트를 감지하여 백업 데이터 처리를 실행하는 백그라운드 태스크
        """
        while True:
            try:
                await self._db_reconnected_event.wait() # 이벤트 발생 대기
                
                async with self._backup_processing_lock:
                    logger.info("DB 재연결 신호 감지. 백업 데이터 처리를 시작합니다.")
                    
                    try:
                        # 각 Repository의 백업 처리 메서드를 직접 호출
                        if self.alert_repository:
                            await self.alert_repository.process_pending_log_backups()
                        
                        if self.sensor_repository:
                            await self.sensor_repository.process_pending_backups()

                        logger.info("백업 데이터 처리 완료.")
                    except Exception as e:
                        logger.error(f"백업 데이터 처리 중 오류 발생: {e}")
                    finally:
                        self._db_reconnected_event.clear() # 다음 신호를 위해 이벤트 초기화

            except asyncio.CancelledError:
                logger.info("백업 처리 태스크가 종료됩니다.")
                break
            except Exception as e:
                logger.error(f"백업 처리 태스크에서 예상치 못한 오류 발생: {e}")
                await asyncio.sleep(5)

    async def close(self) -> None:
        """데이터베이스 매니저 종료"""
        # 백업 태스크 먼저 취소
        if self._backup_task and not self._backup_task.done():
            self._backup_task.cancel()
            try:
                await self._backup_task
            except asyncio.CancelledError:
                pass
        
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