"""
RSD 모니터링 시스템 로그 관리자
날짜별 단일 로그 파일 생성, 4가지 카테고리 로그 관리
완전 클래스 기반 구조, 전역 함수 완전 배제
의존성 주입 패턴 적용
"""

import logging
from datetime import datetime, timedelta
from pathlib import Path

from config_manager import ConfigManager

# =============================================================================
# 로그 매니저 클래스
# =============================================================================

class LogManager:
    """통합 로그 관리자 - 날짜별 단일 로그 파일과 핵심 4가지 카테고리만 관리"""
    
    def __init__(self, config: ConfigManager):
        """
        로그 매니저 초기화
        
        Args:
            config: 설정 관리자
        """
        self.config = config
        self.log_dir = Path(config.logging_dir)
        self.logger = None
        self._current_log_date = None
        
        self._setup_logging()
    
    def _setup_logging(self) -> None:
        """로깅 시스템 설정"""
        self.log_dir.mkdir(exist_ok=True)
        
        # 루트 로거 설정
        self.logger = logging.getLogger()
        self.logger.setLevel(logging.DEBUG)
        self.logger.handlers.clear()
        
        # 포매터 설정
        formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        
        # 파일 핸들러 설정 (날짜별 단일 파일)
        self._setup_file_handler(formatter)
        
        # 콘솔 핸들러 설정
        if self.config.logging_console_output:
            console_handler = logging.StreamHandler()
            console_handler.setFormatter(formatter)
            console_handler.setLevel(logging.INFO)
            self.logger.addHandler(console_handler)
        
        # 오래된 로그 파일 정리
        self._cleanup_old_logs()
        
        self.operation_log("시스템", "로그 시스템 초기화 완료")
    
    def _setup_file_handler(self, formatter) -> None:
        """파일 핸들러 설정 - 날짜별 단일 파일"""
        current_date = datetime.now().strftime('%Y-%m-%d')
        self._current_log_date = current_date
        
        log_file = self.log_dir / f"{current_date}.log"
        file_handler = logging.FileHandler(log_file, encoding='utf-8', mode='a')
        file_handler.setFormatter(formatter)
        file_handler.setLevel(logging.DEBUG)
        self.logger.addHandler(file_handler)
    
    def _check_date_change(self) -> None:
        """날짜 변경 확인 및 로그 파일 교체"""
        current_date = datetime.now().strftime('%Y-%m-%d')
        if self._current_log_date != current_date:
            # 기존 파일 핸들러 제거
            for handler in self.logger.handlers[:]:
                if isinstance(handler, logging.FileHandler):
                    handler.close()
                    self.logger.removeHandler(handler)
            
            # 새 파일 핸들러 생성
            formatter = logging.Formatter(
                '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
                datefmt='%Y-%m-%d %H:%M:%S'
            )
            self._setup_file_handler(formatter)
    
    def _cleanup_old_logs(self) -> None:
        """오래된 로그 파일 정리"""
        try:
            cutoff_date = datetime.now() - timedelta(days=self.config.logging_max_days_keep)
            
            for log_file in self.log_dir.glob("*.log"):
                try:
                    date_str = log_file.stem
                    file_date = datetime.strptime(date_str, '%Y-%m-%d')
                    
                    if file_date < cutoff_date:
                        log_file.unlink()
                        
                except (ValueError, OSError):
                    continue
                    
        except Exception as e:
            self.error_log("로그정리", f"로그 파일 정리 실패: {e}")
    
    # =========================================================================
    # 핵심 4가지 로그 카테고리
    # =========================================================================
    
    def operation_log(self, operation: str, message: str) -> None:
        """
        동작 로그 기록 (시스템, DB, 모니터링, UI 등)
        
        Args:
            operation: 동작 유형 (시스템, DB, 모니터링, UI 등)
            message: 로그 메시지
        """
        self._check_date_change()
        log_msg = f"[동작] {operation}: {message}"
        self.logger.info(log_msg)
    
    def communication_log(self, string_id: int, rsd_id: int, operation: str, 
                         status: str, duration: float, details: str = "") -> None:
        """
        통신 로그 기록 (RSD 통신 상태 및 결과)
        
        Args:
            string_id: String ID
            rsd_id: RSD ID
            operation: 작업 유형 (sensor_poll, connection_test 등)
            status: 상태 (success, error, timeout 등)
            duration: 소요 시간 (초)
            details: 상세 정보
        """
        self._check_date_change()
        log_msg = f"[통신] String{string_id}/RSD{rsd_id} {operation}: {status} ({duration:.3f}s)"
        if details:
            log_msg += f" - {details}"
        
        if status == "success":
            self.logger.info(log_msg)
        else:
            self.logger.warning(log_msg)
    
    def packet_log(self, string_id: int, rsd_id: int, direction: str, packet_data: str) -> None:
        """
        패킷 로그 기록 (실제 송수신 패킷 데이터)
        
        Args:
            string_id: String ID
            rsd_id: RSD ID
            direction: 방향 (send, recv)
            packet_data: 패킷 데이터 (hex 문자열)
        """
        self._check_date_change()
        if self.config.logging_packet_debug:
            direction_kr = "송신" if direction == "send" else "수신"
            log_msg = f"[패킷] String{string_id}/RSD{rsd_id} {direction_kr}: {packet_data}"
            self.logger.info(log_msg)
    
    def error_log(self, component: str, error_message: str) -> None:
        """
        에러 로그 기록 (시스템 오류 및 예외)
        
        Args:
            component: 컴포넌트명 (통신, DB, 시스템 등)
            error_message: 에러 메시지
        """
        self._check_date_change()
        log_msg = f"[에러] {component}: {error_message}"
        self.logger.error(log_msg)
    
    # =========================================================================
    # 특별 기능: 모니터링 통신 및 아크 감지
    # =========================================================================
    
    def monitoring_communication_log(self, string_id: int, rsd_id: int, 
                                   request_packet: str, response_packet: str, 
                                   duration: float, data_count: int = 0) -> None:
        """
        모니터링 통신 전용 로그 (요청/응답 패킷 쌍으로 기록)
        
        Args:
            string_id: String ID
            rsd_id: RSD ID
            request_packet: 요청 패킷 (hex 문자열)
            response_packet: 응답 패킷 (hex 문자열) 
            duration: 통신 소요 시간 (초)
            data_count: 수집된 데이터 개수
        """
        # 통신 상태 로그
        details = f"{data_count}개 데이터 수집" if data_count > 0 else ""
        self.communication_log(string_id, rsd_id, "monitoring_poll", "success", duration, details)
        
        # 패킷 상세 로그
        self.packet_log(string_id, rsd_id, "send", request_packet)
        self.packet_log(string_id, rsd_id, "recv", response_packet)
    
    def arc_detection_log(self, string_id: int, rsd_id: int, channel_no: int, 
                         arc_frequency: int, arc_count: int) -> None:
        """
        아크 발생 감지 로그 기록
        
        Args:
            string_id: String ID
            rsd_id: RSD ID  
            channel_no: 채널 번호
            arc_frequency: 아크 주파수 (KHz)
            arc_count: 감지 횟수
        """
        self._check_date_change()
        message = f"String{string_id}/RSD{rsd_id} 아크 발생 감지 - CH{channel_no} ({arc_frequency}KHz, {arc_count}회)"
        log_msg = f"[경고] 아크감지: {message}"
        self.logger.warning(log_msg)


# =============================================================================
# 성능 타이머 클래스 (LogManager 의존성 주입)
# =============================================================================

class PerformanceTimer:
    """성능 측정 컨텍스트 매니저"""
    
    def __init__(self, operation: str, log_manager: LogManager, details: str = ""):
        """
        성능 타이머 초기화
        
        Args:
            operation: 측정할 작업명
            log_manager: 로그 매니저 인스턴스  
            details: 상세 설명
        """
        self.operation = operation
        self.log_manager = log_manager
        self.details = details
        self.start_time = None
        self.success = True
    
    def __enter__(self):
        """컨텍스트 시작"""
        self.start_time = datetime.now()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """컨텍스트 종료 및 로그 기록"""
        if self.start_time is None:
            return
        
        duration = (datetime.now() - self.start_time).total_seconds()
        
        if exc_type is not None:
            self.success = False
            error_msg = f"{self.details} - {str(exc_val)}" if self.details else str(exc_val)
        else:
            error_msg = self.details
        
        status = "성공" if self.success else "실패"
        message = f"{self.operation}: {status} ({duration:.3f}s)"
        if error_msg:
            message += f" - {error_msg}"
        
        if self.success:
            self.log_manager.operation_log("성능", message)
        else:
            self.log_manager.error_log("성능", message)
    
    def mark_error(self, error_msg: str = "") -> None:
        """에러 상태로 표시"""
        self.success = False
        if error_msg:
            self.details = error_msg