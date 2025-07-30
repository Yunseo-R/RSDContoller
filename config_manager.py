"""
RSD 모니터링 시스템 설정 관리자
설정 파일(config.ini)의 생성, 파싱, 저장을 담당함.
"""

import os
import configparser
from typing import Any, Optional
from dataclasses import dataclass


# =============================================================================
# 데이터 클래스들
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
        """설정 파일(ini)을 읽어 각 변수에 값을 로드"""
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
        """기본 설정값으로 ConfigParser 객체 생성."""
        self.config.clear()
        
        # 각 섹션 및 키-값 설정
        # Database 섹션
        self.config.add_section('database')
        self.config.set('database', 'host', self.database_host)
        self.config.set('database', 'port', str(self.database_port))
        self.config.set('database', 'database', self.database_name)
        self.config.set('database', 'username', self.database_username)
        self.config.set('database', 'password', self.database_password)
        
        # Monitoring 섹션
        self.config.add_section('monitoring')
        self.config.set('monitoring', 'display_interval', str(self.monitoring_display_interval))
        self.config.set('monitoring', 'communication_interval', str(self.monitoring_communication_interval))
        self.config.set('monitoring', 'save_interval', str(self.monitoring_save_interval))
        self.config.set('monitoring', 'rsd_communication_delay', str(self.monitoring_rsd_communication_delay))
        
        # TCP Communication 섹션
        self.config.add_section('tcp_communication')
        self.config.set('tcp_communication', 'connection_timeout', str(self.tcp_connection_timeout))
        self.config.set('tcp_communication', 'read_timeout', str(self.tcp_read_timeout))
        self.config.set('tcp_communication', 'max_retries', str(self.tcp_max_retries))
        self.config.set('tcp_communication', 'rsd_port', str(self.tcp_rsd_port))
        self.config.set('tcp_communication', 'retry_delay', str(self.tcp_retry_delay))
        self.config.set('tcp_communication', 'socket_reuse', str(self.tcp_socket_reuse).lower())
        self.config.set('tcp_communication', 'buffer_size', str(self.tcp_buffer_size))
        
        # Logging 섹션
        self.config.add_section('logging')
        self.config.set('logging', 'level', self.logging_level)
        self.config.set('logging', 'log_dir', self.logging_dir)
        self.config.set('logging', 'daily_rotation', str(self.logging_daily_rotation).lower())
        self.config.set('logging', 'max_days_keep', str(self.logging_max_days_keep))
        self.config.set('logging', 'console_output', str(self.logging_console_output).lower())
        self.config.set('logging', 'packet_debug', str(self.logging_packet_debug).lower())
        self.config.set('logging', 'communication_detail', str(self.logging_communication_detail).lower())
    
    def _sync_variables_to_config(self) -> None:
        """현재 인스턴스 변수 값을 ConfigParser 객체에 동기화."""
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
        """설정 파일 저장"""
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
    # 데이터베이스 설정 접근 메서드
    # =========================================================================
    
    def get_database_config(self) -> DatabaseConfig:
        """데이터베이스 설정 객체 반환"""
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
        """데이터베이스 설정 업데이트"""
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
    
    # =========================================================================
    # 모니터링 설정 접근 메서드
    # =========================================================================
    
    def update_monitoring_config(self, display_interval: Optional[int] = None,
                             communication_interval: Optional[int] = None,
                             save_interval: Optional[int] = None,
                             rsd_communication_delay: Optional[float] = None) -> None:
        """모니터링 설정 업데이트"""
        if display_interval is not None:
            self.monitoring_display_interval = display_interval
        if communication_interval is not None:
            self.monitoring_communication_interval = communication_interval
        if save_interval is not None:
            self.monitoring_save_interval = save_interval
        if rsd_communication_delay is not None:
            self.monitoring_rsd_communication_delay = rsd_communication_delay
        
        self._save_config()
        print("모니터링 설정이 업데이트되었습니다")

    # =========================================================================
    # TCP 통신 설정 접근 메서드
    # =========================================================================
    
    def update_tcp_config(self, connection_timeout: Optional[float] = None,
                         read_timeout: Optional[float] = None, max_retries: Optional[int] = None,
                         rsd_port: Optional[int] = None, retry_delay: Optional[float] = None,
                         socket_reuse: Optional[bool] = None, buffer_size: Optional[int] = None) -> None:
        """TCP 통신 설정 업데이트"""
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
    
    # =========================================================================
    # 로깅 설정 접근 메서드
    # =========================================================================
    
    def update_logging_config(self, level: Optional[str] = None, log_dir: Optional[str] = None, 
                            daily_rotation: Optional[bool] = None, max_days_keep: Optional[int] = None,
                            console_output: Optional[bool] = None, packet_debug: Optional[bool] = None,
                            communication_detail: Optional[bool] = None) -> None:
        """로깅 설정 업데이트"""
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
    
    def reload_config(self) -> None:
        """설정 파일을 다시 로드하여 현재 설정에 반영."""
        self._load_config()
        print("설정 파일 재로드 완료")
    
    def save_current_config(self) -> None:
        """현재 설정을 파일에 저장"""
        self._save_config()
    
    def log_current_settings(self) -> None:
        """현재 적용된 모든 설정 값을 콘솔에 출력."""
        print("=== 현재 설정 값 ===")
        print(f"DB: {self.database_host}:{self.database_port}/{self.database_name}")
        print(f"모니터링: 표시 {self.monitoring_display_interval}초, 저장 {self.monitoring_save_interval}초, 통신 주기 {self.monitoring_communication_interval}초, 통신간격 {self.monitoring_rsd_communication_delay}초")
        print(f"TCP: 포트 {self.tcp_rsd_port}, 연결 {self.tcp_connection_timeout}초, 읽기 {self.tcp_read_timeout}초, 재시도 {self.tcp_max_retries}회")
        print(f"로깅: {self.logging_level} 레벨, 디렉토리 '{self.logging_dir}', 패킷디버깅 {self.logging_packet_debug}")
        print("==================")