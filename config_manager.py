"""
RSD 모니터링 시스템 설정 관리자
설정 파일(config.ini)의 생성, 파싱, 저장을 담당
각 설정 항목에 대한 기본값을 정의 및 유효성 검증
"""

import os
import configparser
from typing import Optional, List
from dataclasses import dataclass


# =============================================================================
# 데이터 클래스
# =============================================================================

@dataclass
class DatabaseConfig:
    """데이터베이스 연결 설정 정보 저장"""
    host: str
    port: int
    database: str
    username: str
    password: str


# =============================================================================
# 설정 관리자 클래스
# =============================================================================

class ConfigManager:
    """RSD 모니터링 시스템 설정 관리자"""
    
    def __init__(self, config_path: str = "config.ini"):
        """
        설정 관리자 초기화
        
        Args:
            config_path: 설정 파일 경로
        """
        self.config_path = config_path
        self.config = configparser.ConfigParser()
        
        # 기본 설정값 정의
        self._init_default_values()
        
        # 설정 파일 로드 또는 생성
        self._load_or_create_config()
    
    def _init_default_values(self) -> None:
        """설정 파일 생성시 모든 설정 항목의 기본값 초기화"""
        # 데이터베이스 설정
        self.database_host = "192.168.10.8"
        self.database_port = 5432
        self.database_name = "RSD_DB"
        self.database_username = "irsd"
        self.database_password = "prsd!2345"
        
        # 모니터링 설정
        self.monitoring_display_interval = 30
        self.monitoring_communication_interval = 30
        self.monitoring_save_interval = 30
        self.monitoring_rsd_communication_delay = 0.5
        
        # TCP 통신 설정
        self.tcp_connection_timeout = 5.0
        self.tcp_read_timeout = 3.0
        self.tcp_max_retries = 3
        self.tcp_rsd_port = 4001
        self.tcp_retry_delay = 1.0
        self.tcp_socket_reuse = True
        self.tcp_buffer_size = 1024
        
        # 로깅 설정
        self.logging_level = "INFO"
        self.logging_dir = "logs"
        self.logging_daily_rotation = True
        self.logging_max_days_keep = 30
        self.logging_console_output = True
        self.logging_packet_debug = False
        self.logging_communication_detail = False
    
    def _load_or_create_config(self) -> None:
        """설정 파일 로드, 없을 시 기본값으로 생성"""
        if os.path.exists(self.config_path):
            print(f"기존 설정 파일 로드: {self.config_path}")
            self._load_config()
        else:
            print(f"설정 파일이 없습니다. 기본 설정으로 파일을 생성합니다: {self.config_path}")
            self._create_default_config()
            self._save_config()
            print("기본 설정 파일이 생성되었습니다.")
    
    def _load_config(self) -> None:
        """
        설정 파일(config.ini)에서 각 섹션의 값을 읽어와 변수에 할당
        fallback을 사용하여 파일에 값이 없을 경우 기본값 유지
        """
        try:
            self.config.read(self.config_path, encoding='utf-8')
            
            # 데이터베이스 설정 로드
            if self.config.has_section('database'):
                self.database_host = self.config.get('database', 'host', fallback=self.database_host)
                self.database_port = self.config.getint('database', 'port', fallback=self.database_port)
                self.database_name = self.config.get('database', 'database', fallback=self.database_name)
                self.database_username = self.config.get('database', 'username', fallback=self.database_username)
                self.database_password = self.config.get('database', 'password', fallback=self.database_password)
            
            # 모니터링 설정 로드
            if self.config.has_section('monitoring'):
                self.monitoring_display_interval = self.config.getint('monitoring', 'display_interval', fallback=self.monitoring_display_interval)
                self.monitoring_communication_interval = self.config.getint('monitoring', 'communication_interval', fallback=self.monitoring_communication_interval)
                self.monitoring_save_interval = self.config.getint('monitoring', 'save_interval', fallback=self.monitoring_save_interval)
                self.monitoring_rsd_communication_delay = self.config.getfloat('monitoring', 'rsd_communication_delay', fallback=self.monitoring_rsd_communication_delay)
            
            # TCP 통신 설정 로드
            if self.config.has_section('tcp_communication'):
                self.tcp_connection_timeout = self.config.getfloat('tcp_communication', 'connection_timeout', fallback=self.tcp_connection_timeout)
                self.tcp_read_timeout = self.config.getfloat('tcp_communication', 'read_timeout', fallback=self.tcp_read_timeout)
                self.tcp_max_retries = self.config.getint('tcp_communication', 'max_retries', fallback=self.tcp_max_retries)
                self.tcp_rsd_port = self.config.getint('tcp_communication', 'rsd_port', fallback=self.tcp_rsd_port)
                self.tcp_retry_delay = self.config.getfloat('tcp_communication', 'retry_delay', fallback=self.tcp_retry_delay)
                self.tcp_socket_reuse = self.config.getboolean('tcp_communication', 'socket_reuse', fallback=self.tcp_socket_reuse)
                self.tcp_buffer_size = self.config.getint('tcp_communication', 'buffer_size', fallback=self.tcp_buffer_size)
            
            # 로깅 설정 로드
            if self.config.has_section('logging'):
                self.logging_level = self.config.get('logging', 'level', fallback=self.logging_level)
                self.logging_dir = self.config.get('logging', 'log_dir', fallback=self.logging_dir)
                self.logging_daily_rotation = self.config.getboolean('logging', 'daily_rotation', fallback=self.logging_daily_rotation)
                self.logging_max_days_keep = self.config.getint('logging', 'max_days_keep', fallback=self.logging_max_days_keep)
                self.logging_console_output = self.config.getboolean('logging', 'console_output', fallback=self.logging_console_output)
                self.logging_packet_debug = self.config.getboolean('logging', 'packet_debug', fallback=self.logging_packet_debug)
                self.logging_communication_detail = self.config.getboolean('logging', 'communication_detail', fallback=self.logging_communication_detail)
                
        except Exception as e:
            print(f"설정 파싱 중 오류 발생: {e}")
            print("일부 설정이 기본값으로 사용됩니다")

    def _create_default_config(self) -> None:
        """기본값으로 ConfigParser 객체 구성"""
        self._sync_variables_to_config()

    def _sync_variables_to_config(self) -> None:
        """현재 변수값들을 ConfigParser 객체에 동기화"""
        # Database 섹션
        if not self.config.has_section('database'):
            self.config.add_section('database')
        self.config.set('database', 'host', self.database_host)
        self.config.set('database', 'port', str(self.database_port))
        self.config.set('database', 'database', self.database_name)
        self.config.set('database', 'username', self.database_username)
        self.config.set('database', 'password', self.database_password)
        
        # Monitoring 섹션
        if not self.config.has_section('monitoring'):
            self.config.add_section('monitoring')
        self.config.set('monitoring', 'display_interval', str(self.monitoring_display_interval))
        self.config.set('monitoring', 'communication_interval', str(self.monitoring_communication_interval))
        self.config.set('monitoring', 'save_interval', str(self.monitoring_save_interval))
        self.config.set('monitoring', 'rsd_communication_delay', str(self.monitoring_rsd_communication_delay))
        
        # TCP Communication 섹션
        if not self.config.has_section('tcp_communication'):
            self.config.add_section('tcp_communication')
        self.config.set('tcp_communication', 'connection_timeout', str(self.tcp_connection_timeout))
        self.config.set('tcp_communication', 'read_timeout', str(self.tcp_read_timeout))
        self.config.set('tcp_communication', 'max_retries', str(self.tcp_max_retries))
        self.config.set('tcp_communication', 'rsd_port', str(self.tcp_rsd_port))
        self.config.set('tcp_communication', 'retry_delay', str(self.tcp_retry_delay))
        self.config.set('tcp_communication', 'socket_reuse', str(self.tcp_socket_reuse).lower())
        self.config.set('tcp_communication', 'buffer_size', str(self.tcp_buffer_size))
        
        # Logging 섹션
        if not self.config.has_section('logging'):
            self.config.add_section('logging')
        self.config.set('logging', 'level', self.logging_level)
        self.config.set('logging', 'log_dir', self.logging_dir)
        self.config.set('logging', 'daily_rotation', str(self.logging_daily_rotation).lower())
        self.config.set('logging', 'max_days_keep', str(self.logging_max_days_keep))
        self.config.set('logging', 'console_output', str(self.logging_console_output).lower())
        self.config.set('logging', 'packet_debug', str(self.logging_packet_debug).lower())
        self.config.set('logging', 'communication_detail', str(self.logging_communication_detail).lower())
    
    def _save_config(self) -> None:
        """현재 설정값들을 config.ini 파일에 저장"""
        try:
            # 현재 변수값들을 config 객체에 동기화
            self._sync_variables_to_config()
            
            # 파일 경로의 디렉터리가 없으면 생성
            os.makedirs(os.path.dirname(self.config_path) if os.path.dirname(self.config_path) else '.', exist_ok=True)
            
            # 파일에 저장
            with open(self.config_path, 'w', encoding='utf-8') as configfile:
                self.config.write(configfile)
                
        except Exception as e:
            print(f"설정 파일 저장 실패: {e}")
    
# =========================================================================
# 설정 접근 및 관리 메서드
# =========================================================================

# ----------------- 데이터베이스 설정 -----------------
    def get_database_config(self) -> DatabaseConfig:
        """데이터베이스 설정을 DatabaseConfig 객체로 반환"""
        return DatabaseConfig(
            host=self.database_host,
            port=self.database_port,
            database=self.database_name,
            username=self.database_username,
            password=self.database_password
        )
    
    def update_database_config(self, host: Optional[str] = None, port: Optional[int] = None,
                             database: Optional[str] = None, username: Optional[str] = None,
                             password: Optional[str] = None) -> None:
        """
        데이터베이스 설정 업데이트 및 파일에 즉시 저장

        Args:
            host: DB 호스트 주소
            port: DB 포트 번호
            database: 데이터베이스 이름
            username: 사용자 이름
            password: 비밀번호
        """
        if host is not None:
            self.database_host = host
        if port is not None:
            self.database_port = port
        if database is not None:
            self.database_name = database
        if username is not None:
            self.database_username = username
        if password is not None:
            self.database_password = password
        
        self._save_config()
        print("데이터베이스 설정이 업데이트되었습니다")
    
# -----------------모니터링 설정-----------------
    def update_monitoring_settings(self, communication_interval: Optional[int] = None,
                                 display_interval: Optional[int] = None,
                                 save_interval: Optional[int] = None,
                                 rsd_communication_delay: Optional[float] = None) -> None:
        """
        모니터링 설정 업데이트 및 파일에 즉시 저장

        Args:
            communication_interval: 통신 주기 (초).
            display_interval 화면 갱신 주기 (초).
            save_interval: DB 저장 주기 (초).
            rsd_communication_delay: RSD 장치 간 통신 지연 시간 (초).
        """
        if communication_interval is not None:
            self.monitoring_communication_interval = communication_interval
        if display_interval is not None:
            self.monitoring_display_interval = display_interval
        if save_interval is not None:
            self.monitoring_save_interval = save_interval
        if rsd_communication_delay is not None:
            self.monitoring_rsd_communication_delay = rsd_communication_delay
        
        self._save_config()
        print("모니터링 설정이 업데이트되었습니다")
    
    def get_monitoring_intervals(self) -> dict:
        """모니터링 간격 설정 딕셔너리 형태로 반환"""
        return {
            'communication_interval': self.monitoring_communication_interval,
            'display_interval': self.monitoring_display_interval,
            'save_interval': self.monitoring_save_interval,
            'rsd_communication_delay': self.monitoring_rsd_communication_delay
        }
    
# ----------------- TCP 통신 설정 -----------------
    def update_tcp_settings(self, connection_timeout: Optional[float] = None,
                          read_timeout: Optional[float] = None,
                          max_retries: Optional[int] = None,
                          rsd_port: Optional[int] = None,
                          retry_delay: Optional[float] = None,
                          socket_reuse: Optional[bool] = None,
                          buffer_size: Optional[int] = None) -> None:
        """
        TCP 통신 관련 설정 업데이트 및 파일에 즉시 저장

        Args:
            connection_timeout: 연결 타임아웃 (초)
            read_timeout: 읽기 타임아웃 (초)
            max_retries: 최대 재시도 횟수
            rsd_port: RSD 통신 포트
            retry_delay: 재시도 간 지연 시간 (초)
            socket_reuse: 소켓 재사용 여부
            buffer_size: 통신 버퍼 크기
        """
        if connection_timeout is not None:
            self.tcp_connection_timeout = connection_timeout
        if read_timeout is not None:
            self.tcp_read_timeout = read_timeout
        if max_retries is not None:
            self.tcp_max_retries = max_retries
        if rsd_port is not None:
            self.tcp_rsd_port = rsd_port
        if retry_delay is not None:
            self.tcp_retry_delay = retry_delay
        if socket_reuse is not None:
            self.tcp_socket_reuse = socket_reuse
        if buffer_size is not None:
            self.tcp_buffer_size = buffer_size
        
        self._save_config()
        print("TCP 통신 설정이 업데이트되었습니다")
    
    def get_tcp_settings(self) -> dict:
        """TCP 통신 설정 딕셔너리 형태로 반환"""
        return {
            'connection_timeout': self.tcp_connection_timeout,
            'read_timeout': self.tcp_read_timeout,
            'max_retries': self.tcp_max_retries,
            'rsd_port': self.tcp_rsd_port,
            'retry_delay': self.tcp_retry_delay,
            'socket_reuse': self.tcp_socket_reuse,
            'buffer_size': self.tcp_buffer_size
        }
    
# ----------------- 로깅 설정 -----------------
    def update_logging_settings(self, level: Optional[str] = None,
                              log_dir: Optional[str] = None,
                              daily_rotation: Optional[bool] = None,
                              max_days_keep: Optional[int] = None,
                              console_output: Optional[bool] = None,
                              packet_debug: Optional[bool] = None,
                              communication_detail: Optional[bool] = None) -> None:
        """
        로깅 설정 업데이트 및 파일에 즉시 저장

        Args:
            level: 로그 레벨 (e.g., "INFO", "DEBUG")
            log_dir: 로그 파일 저장 디렉터리
            daily_rotation: 로그 파일을 매일 새로 생성할지 여부
            max_days_keep: 로그 파일 보관 최대 일수
            console_output: 콘솔에 로그를 출력할지 여부
            packet_debug: 통신 패킷 내용을 로그로 남길지 여부
            communication_detail: 상세 통신 과정을 로그로 남길지 여부
        """
        if level is not None:
            self.logging_level = level
        if log_dir is not None:
            self.logging_dir = log_dir
        if daily_rotation is not None:
            self.logging_daily_rotation = daily_rotation
        if max_days_keep is not None:
            self.logging_max_days_keep = max_days_keep
        if console_output is not None:
            self.logging_console_output = console_output
        if packet_debug is not None:
            self.logging_packet_debug = packet_debug
        if communication_detail is not None:
            self.logging_communication_detail = communication_detail
        
        self._save_config()
        print("로깅 설정이 업데이트되었습니다")
    
    def get_logging_settings(self) -> dict:
        """로깅 설정 딕셔너리 형태로 반환"""
        return {
            'level': self.logging_level,
            'log_dir': self.logging_dir,
            'daily_rotation': self.logging_daily_rotation,
            'max_days_keep': self.logging_max_days_keep,
            'console_output': self.logging_console_output,
            'packet_debug': self.logging_packet_debug,
            'communication_detail': self.logging_communication_detail
        }
    
    # =========================================================================
    # 설정 파일 관리 유틸리티 메서드
    # =========================================================================
    
    def reload_config(self) -> bool:
        """설정 파일 다시 로드"""
        try:
            self._load_config()
            print("설정 파일이 다시 로드되었습니다")
            return True
        except Exception as e:
            print(f"설정 파일 로드 실패: {e}")
            return False
    
    def reset_to_defaults(self) -> None:
        """모든 설정을 기본값으로 초기화"""
        self._init_default_values()
        self._save_config()
        print("모든 설정이 기본값으로 초기화되었습니다")
    
    def export_config(self, export_path: str) -> bool:
        """현재 설정을 다른 파일로 내보내기"""
        try:
            self._sync_variables_to_config()
            
            # 내보낼 경로에 디렉터리가 없으면 생성
            os.makedirs(os.path.dirname(export_path) if os.path.dirname(export_path) else '.', exist_ok=True)
            
            with open(export_path, 'w', encoding='utf-8') as configfile:
                self.config.write(configfile)
            
            print(f"설정이 {export_path}로 내보내기되었습니다")
            return True
        except Exception as e:
            print(f"설정 내보내기 실패: {e}")
            return False
    
    def import_config(self, import_path: str) -> bool:
        """다른 파일에서 설정 가져오기"""
        try:
            if not os.path.exists(import_path):
                print(f"설정 파일이 존재하지 않습니다: {import_path}")
                return False
            
            # 임시 ConfigParser로 파일 유효성 검증
            temp_config = configparser.ConfigParser()
            temp_config.read(import_path, encoding='utf-8')
            
            # 검증 성공 시 현재 설정 파일 경로에 복사
            import shutil
            shutil.copy2(import_path, self.config_path)
            
            # 설정 다시 로드
            self._load_config()
            
            print(f"설정이 {import_path}에서 가져와졌습니다")
            return True
        except Exception as e:
            print(f"설정 가져오기 실패: {e}")
            return False
    
    def validate_config(self) -> List[str]:
        """설정값 유효성 검증"""
        errors = []
        
        # 데이터베이스 설정 검증
        if not self.database_host:
            errors.append("데이터베이스 호스트가 설정되지 않았습니다")
        if not (1 <= self.database_port <= 65535):
            errors.append("데이터베이스 포트가 유효하지 않습니다 (1-65535)")
        if not self.database_name:
            errors.append("데이터베이스 이름이 설정되지 않았습니다")
        if not self.database_username:
            errors.append("데이터베이스 사용자명이 설정되지 않았습니다")
        
        # 모니터링 설정 검증
        if self.monitoring_communication_interval <= 0:
            errors.append("통신 간격은 0보다 커야 합니다")
        if self.monitoring_display_interval <= 0:
            errors.append("표시 간격은 0보다 커야 합니다")
        if self.monitoring_save_interval <= 0:
            errors.append("저장 간격은 0보다 커야 합니다")
        if self.monitoring_rsd_communication_delay < 0:
            errors.append("RSD 통신 지연은 0 이상이어야 합니다")
        
        # TCP 설정 검증
        if self.tcp_connection_timeout <= 0:
            errors.append("연결 타임아웃은 0보다 커야 합니다")
        if self.tcp_read_timeout <= 0:
            errors.append("읽기 타임아웃은 0보다 커야 합니다")
        if not (1 <= self.tcp_rsd_port <= 65535):
            errors.append("RSD 포트가 유효하지 않습니다 (1-65535)")
        if self.tcp_max_retries < 0:
            errors.append("최대 재시도 횟수는 0 이상이어야 합니다")
        if self.tcp_buffer_size <= 0:
            errors.append("버퍼 크기는 0보다 커야 합니다")
        
        # 로깅 설정 검증
        valid_log_levels = ['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL']
        if self.logging_level.upper() not in valid_log_levels:
            errors.append(f"로그 레벨이 유효하지 않습니다. 사용 가능한 레벨: {', '.join(valid_log_levels)}")
        if self.logging_max_days_keep <= 0:
            errors.append("로그 보관 일수는 0보다 커야 합니다")
        
        return errors
    
    def print_current_config(self) -> None:
        """현재 설정 출력"""
        print("\n=== 현재 설정 ===")
        print(f"[데이터베이스]")
        print(f"  호스트: {self.database_host}")
        print(f"  포트: {self.database_port}")
        print(f"  데이터베이스: {self.database_name}")
        print(f"  사용자명: {self.database_username}")
        print(f"  비밀번호: {'*' * len(self.database_password)}")
        
        print(f"\n[모니터링]")
        print(f"  통신 간격: {self.monitoring_communication_interval}초")
        print(f"  표시 간격: {self.monitoring_display_interval}초")
        print(f"  저장 간격: {self.monitoring_save_interval}초")
        print(f"  RSD 통신 지연: {self.monitoring_rsd_communication_delay}초")
        
        print(f"\n[TCP 통신]")
        print(f"  연결 타임아웃: {self.tcp_connection_timeout}초")
        print(f"  읽기 타임아웃: {self.tcp_read_timeout}초")
        print(f"  최대 재시도: {self.tcp_max_retries}회")
        print(f"  RSD 포트: {self.tcp_rsd_port}")
        print(f"  재시도 지연: {self.tcp_retry_delay}초")
        print(f"  소켓 재사용: {self.tcp_socket_reuse}")
        print(f"  버퍼 크기: {self.tcp_buffer_size}")
        
        print(f"\n[로깅]")
        print(f"  레벨: {self.logging_level}")
        print(f"  디렉터리: {self.logging_dir}")
        print(f"  일별 회전: {self.logging_daily_rotation}")
        print(f"  보관 일수: {self.logging_max_days_keep}일")
        print(f"  콘솔 출력: {self.logging_console_output}")
        print(f"  패킷 디버그: {self.logging_packet_debug}")
        print(f"  통신 상세: {self.logging_communication_detail}")
        print("================\n")