"""
RSD 실시간 모니터링 메인 애플리케이션
PySide6 기반 실시간 센싱 데이터 표시
완전 클래스 기반 구조, LogManager 의존성 주입 적용
"""

import sys
import asyncio
import logging
import os
import signal
from typing import Dict, List, Optional, Any
from datetime import datetime, timedelta

from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, 
    QGridLayout, QLabel, QFrame, QScrollArea, QPushButton, QStatusBar,
    QTableWidget, QTableWidgetItem, QHeaderView, QGroupBox, QMessageBox,
    QDialog, QComboBox, QFormLayout, QDialogButtonBox, QMenuBar, QMenu,
    QProgressBar, QSplashScreen
)
from PySide6.QtCore import QTimer, Signal, QThread, Qt, QPropertyAnimation, QEasingCurve
from PySide6.QtGui import QFont, QColor, QAction, QMovie, QPixmap, QPainter


# 모듈 구조 import - DatabaseManager 팩토리 패턴 준수
try:
    from config_manager import ConfigManager, DatabaseConfig
    from db_manager import DatabaseManager, ChannelData, RSDSensorData, StringInfo, DeviceInfo
    from set_string import (
        StringManager,
        RSDManager, 
        RSDTestManager
    )
    from communication import CommunicationManager
    from log import LogManager
    
    print("모듈 로드 완료")
    print("완전 클래스 기반 RSD 모니터링 시스템")
    print("DatabaseManager 팩토리 패턴 준수")
    
    logger = logging.getLogger(__name__)
    LOGGING_AVAILABLE = True
    
except ImportError as e:
    print(f"모듈 import 오류: {e}")
    print("필수 모듈 파일들을 확인해주세요.")
    LOGGING_AVAILABLE = False
    logger = None


# =============================================================================
# 애플리케이션 설정 관리 클래스
# =============================================================================

class AppSettings:
    """애플리케이션 설정 상수 클래스"""
    
    # 기본 설정값
    DEFAULT_WINDOW_WIDTH = 1200
    DEFAULT_WINDOW_HEIGHT = 800
    DEFAULT_WINDOW_X = 100
    DEFAULT_WINDOW_Y = 100
    
    # 타임아웃 설정
    THREAD_STOP_TIMEOUT = 5000  # 5초
    THREAD_TERMINATE_TIMEOUT = 2000  # 2초
    FINAL_CLEANUP_DELAY = 1000  # 1초
    
    # 디스플레이 설정
    DISPLAY_INTERVALS = [30, 60, 120, 180]
    DISPLAY_INTERVAL_LABELS = ["30초", "1분", "2분", "3분"]
    
    SAVE_INTERVALS = [60, 300, 600, 1200]
    SAVE_INTERVAL_LABELS = ["1분", "5분", "10분", "20분"]
    
    # 통신 간격 설정 (새로 추가)
    COMMUNICATION_INTERVALS = [30, 60, 120, 180, 300]
    COMMUNICATION_INTERVAL_LABELS = ["30초", "1분", "2분", "3분", "5분"]
    
    # 통계 업데이트 주기
    STATS_UPDATE_CYCLE = 10

# =============================================================================
# GUI 위젯 클래스들
# =============================================================================

class RSDChannelWidget(QFrame):
    """개별 채널 데이터 표시 위젯 - 컴팩트 버전"""
    
    def __init__(self, channel_no: int):
        super().__init__()
        self.channel_no = channel_no
        self.setup_ui()
        
    def setup_ui(self):
        """UI 구성"""
        self.setFrameStyle(QFrame.Box)
        self.setStyleSheet("""
            QFrame {
                background-color: #ffffff;
                border: 1px solid #e9ecef;
                border-radius: 8px;
                margin: 1px;
            }
        """)
        self.setFixedHeight(80)
        
        layout = QVBoxLayout(self)
        layout.setSpacing(4)
        layout.setContentsMargins(8, 6, 8, 6)
        
        # 채널 번호 헤더
        channel_label = QLabel(f"CH{self.channel_no}")
        channel_label.setFont(QFont("Arial", 7, QFont.Bold))
        channel_label.setStyleSheet("color: #6c757d; font-weight: bold;")
        channel_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(channel_label)
        
        # 데이터 표시 영역
        data_layout = QVBoxLayout()
        data_layout.setSpacing(3)
        data_layout.setContentsMargins(0, 0, 0, 0)
        
        # 온도
        temp_layout = QHBoxLayout()
        temp_layout.setContentsMargins(0, 0, 0, 0)
        temp_label = QLabel("온도:")
        temp_label.setFont(QFont("Arial", 8))
        temp_label.setStyleSheet("color: #6c757d;")
        self.temp_value = QLabel("--°C")
        self.temp_value.setFont(QFont("Arial", 9, QFont.Bold))
        self.temp_value.setStyleSheet("color: #212529;")
        temp_layout.addWidget(temp_label)
        temp_layout.addWidget(self.temp_value)
        temp_layout.addStretch()
        
        # 전류
        current_layout = QHBoxLayout()
        current_layout.setContentsMargins(0, 0, 0, 0)
        current_label = QLabel("전류:")
        current_label.setFont(QFont("Arial", 8))
        current_label.setStyleSheet("color: #6c757d;")
        self.current_value = QLabel("--A")
        self.current_value.setFont(QFont("Arial", 9, QFont.Bold))
        self.current_value.setStyleSheet("color: #212529;")
        current_layout.addWidget(current_label)
        current_layout.addWidget(self.current_value)
        current_layout.addStretch()
        
        # 아크 상태
        arc_layout = QHBoxLayout()
        arc_layout.setContentsMargins(0, 0, 0, 0)
        arc_label = QLabel("아크:")
        arc_label.setFont(QFont("Arial", 8))
        arc_label.setStyleSheet("color: #6c757d;")
        self.arc_status = QLabel("정상")
        self.arc_status.setFont(QFont("Arial", 8, QFont.Bold))
        self.arc_status.setStyleSheet("""
            color: white; 
            background-color: #28a745; 
            border-radius: 4px; 
            padding: 2px 6px;
            min-width: 30px;
        """)
        self.arc_status.setAlignment(Qt.AlignCenter)
        arc_layout.addWidget(arc_label)
        arc_layout.addWidget(self.arc_status)
        arc_layout.addStretch()
        
        data_layout.addLayout(temp_layout)
        data_layout.addLayout(current_layout)
        data_layout.addLayout(arc_layout)
        
        layout.addLayout(data_layout)
        
    def update_data(self, channel_data: ChannelData):
        """채널 데이터 업데이트"""
        self.temp_value.setText(f"{channel_data.temperature:.0f}°C")
        self.current_value.setText(f"{channel_data.current:.0f}A")
        
        if channel_data.is_arc:
            self.arc_status.setText("발생")
            self.arc_status.setStyleSheet("""
                font-size: 8px; 
                font-weight: bold; 
                color: white; 
                background-color: #dc3545; 
                border-radius: 4px; 
                padding: 2px 6px;
                min-width: 30px;
            """)
        else:
            self.arc_status.setText("정상")
            self.arc_status.setStyleSheet("""
                font-size: 8px; 
                font-weight: bold; 
                color: white; 
                background-color: #28a745; 
                border-radius: 4px; 
                padding: 2px 6px;
                min-width: 30px;
            """)


class RSDCompactWidget(QFrame):
    """컴팩트한 RSD 위젯"""
    
    def __init__(self, rsd_id: int, device_name: str = ""):
        super().__init__()
        self.rsd_id = rsd_id
        self.device_name = device_name
        self.channel_widgets = {}
        self.setup_ui()
        
    def setup_ui(self):
        """UI 구성"""
        self.setFrameStyle(QFrame.Box)
        self.setStyleSheet("""
            QFrame {
                background-color: white;
                border: 1px solid #ced4da;
                border-radius: 8px;
                margin: 2px;
            }
        """)
        self.setFixedHeight(115)
        
        layout = QVBoxLayout(self)
        layout.setSpacing(2)
        layout.setContentsMargins(6, 4, 6, 4)
        
        # RSD 헤더
        header_layout = QHBoxLayout()
        header_layout.setContentsMargins(0, 0, 0, 0)
        
        rsd_label = QLabel(f"RSD #{self.rsd_id}")
        rsd_label.setFont(QFont("Arial", 10, QFont.Bold))
        rsd_label.setStyleSheet("color: #343a40; font-weight: bold;")
        
        if self.device_name:
            device_label = QLabel(f"({self.device_name})")
            device_label.setFont(QFont("Arial", 8))
            device_label.setStyleSheet("color: #6c757d;")
            header_layout.addWidget(rsd_label)
            header_layout.addWidget(device_label)
        else:
            header_layout.addWidget(rsd_label)
        
        header_layout.addStretch()
        layout.addLayout(header_layout)
        
        # 채널들 가로 배열
        channels_layout = QHBoxLayout()
        channels_layout.setSpacing(2)
        channels_layout.setContentsMargins(0, 0, 0, 0)
        
        # 기본적으로 2개 채널 위젯 생성
        for channel_no in [1, 2]:
            channel_widget = RSDChannelWidget(channel_no)
            self.channel_widgets[channel_no] = channel_widget
            channels_layout.addWidget(channel_widget)
            
        layout.addLayout(channels_layout)
        
    def update_data(self, rsd_data: RSDSensorData):
        """RSD 데이터 업데이트"""
        for channel_data in rsd_data.channels:
            channel_no = channel_data.channel_no
            if channel_no in self.channel_widgets:
                self.channel_widgets[channel_no].update_data(channel_data)


class StringGroupWidget(QGroupBox):
    """String 그룹 위젯 - 같은 String의 RSD들을 묶어서 표시"""
    
    def __init__(self, string_id: int, string_info: StringInfo = None):
        super().__init__()
        self.string_id = string_id
        self.string_info = string_info
        self.rsd_widgets = {}
        self.setup_ui()
        
    def setup_ui(self):
        """UI 구성"""
        # 제목 설정
        if self.string_info:
            ip = self.string_info.static_ip
            description = self.string_info.description
            title = f"String #{self.string_id} - {ip}"
            if description:
                title += f" ({description})"
        else:
            title = f"String #{self.string_id}"
        
        self.setTitle(title)
        
        self.setFont(QFont("Arial", 11, QFont.Bold))
        self.setStyleSheet("""
            QGroupBox {
                font-weight: bold;
                border: 2px solid #007bff;
                border-radius: 12px;
                margin-top: 12px;
                padding-top: 8px;
                background-color: #f8f9fa;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 15px;
                padding: 0 8px 0 8px;
                color: #007bff;
                background-color: #f8f9fa;
            }
        """)
        
        # RSD들을 격자 형태로 배치
        self.rsd_layout = QGridLayout(self)
        self.rsd_layout.setSpacing(3)
        self.rsd_layout.setContentsMargins(8, 12, 8, 8)
        
        # 컬럼 수 설정
        self.max_columns = 4
        
    def add_rsd_widget(self, rsd_id: int, device_name: str = ""):
        """RSD 위젯 추가"""
        if rsd_id not in self.rsd_widgets:
            rsd_widget = RSDCompactWidget(rsd_id, device_name)
            self.rsd_widgets[rsd_id] = rsd_widget
            
            # 격자 위치 계산
            rsd_count = len(self.rsd_widgets) - 1
            row = rsd_count // self.max_columns
            col = rsd_count % self.max_columns
            
            self.rsd_layout.addWidget(rsd_widget, row, col)
        
        return self.rsd_widgets[rsd_id]
    
    def update_rsd_data(self, rsd_data: RSDSensorData):
        """RSD 데이터 업데이트"""
        rsd_id = rsd_data.rsd_id
        device_name = getattr(rsd_data, 'device_name', '')
        
        # RSD 위젯이 없으면 추가
        if rsd_id not in self.rsd_widgets:
            self.add_rsd_widget(rsd_id, device_name)
        
        # 데이터 업데이트
        self.rsd_widgets[rsd_id].update_data(rsd_data)
    
    def get_rsd_count(self):
        """현재 String의 RSD 개수 반환"""
        return len(self.rsd_widgets)


class LoadingOverlay(QWidget):
    """로딩 오버레이 위젯"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WA_NoSystemBackground)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        
        if parent:
            parent.installEventFilter(self)
            
        self.setAttribute(Qt.WA_DeleteOnClose, False)
        self.setMouseTracking(True)
        self.setAttribute(Qt.WA_NoMousePropagation, False)
        self.setFocusPolicy(Qt.NoFocus)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.setStyleSheet("background-color: rgba(0, 0, 0, 100);")
        
        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignCenter)
        
        # 로딩 메시지
        self.loading_label = QLabel("시스템 초기화 중...")
        self.loading_label.setFont(QFont("Arial", 16, QFont.Bold))
        self.loading_label.setStyleSheet("""
            color: white;
            background-color: rgba(0, 123, 255, 200);
            padding: 20px 40px;
            border-radius: 10px;
            margin-bottom: 20px;
        """)
        self.loading_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.loading_label)
        
        # 상세 메시지
        self.detail_label = QLabel("DB에서 String/RSD 데이터를 로드하고 있습니다...")
        self.detail_label.setFont(QFont("Arial", 12))
        self.detail_label.setStyleSheet("color: white; margin-top: 10px;")
        self.detail_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.detail_label)
        
        self.hide()
    
    def show_loading(self, title="초기화 중...", detail="작업을 진행하고 있습니다..."):
        """로딩 화면 표시"""
        self.loading_label.setText(title)
        self.detail_label.setText(detail)
        self.show()
        self.raise_()
    
    def hide_loading(self):
        """로딩 화면 숨김"""
        self.hide()
    
    def update_message(self, title=None, detail=None):
        """메시지 업데이트"""
        if title:
            self.loading_label.setText(title)
        if detail:
            self.detail_label.setText(detail)

class SettingsDialog(QDialog):
    """설정 다이얼로그"""
    
    def __init__(self, config_manager: ConfigManager, parent=None):
        super().__init__(parent)
        self.config_manager = config_manager
        self.setup_ui()
        
    def setup_ui(self):
        """UI 구성"""
        self.setWindowTitle("RSD 모니터링 설정")
        self.setFixedSize(450, 450)  # 크기 증가
        
        layout = QVBoxLayout(self)
        
        # 제목
        title_label = QLabel("모니터링 설정")
        title_label.setFont(QFont("Arial", 16, QFont.Bold))
        title_label.setAlignment(Qt.AlignCenter)
        title_label.setStyleSheet("color: #343a40; margin-bottom: 15px;")
        layout.addWidget(title_label)
        
        # 설정 폼
        form_layout = QFormLayout()
        form_layout.setSpacing(15)
        
        # 통신 간격 설정 (새로 추가)
        self.communication_combo = QComboBox()
        self.communication_combo.addItems(AppSettings.COMMUNICATION_INTERVAL_LABELS)
        self.communication_combo.setStyleSheet("""
            QComboBox {
                padding: 8px;
                border: 1px solid #ced4da;
                border-radius: 4px;
                background-color: white;
                min-width: 120px;
            }
            QComboBox:focus {
                border-color: #007bff;
            }
        """)
        form_layout.addRow("통신 주기:", self.communication_combo)
        
        # 표시 주기 설정
        self.display_combo = QComboBox()
        self.display_combo.addItems(AppSettings.DISPLAY_INTERVAL_LABELS)
        self.display_combo.setStyleSheet("""
            QComboBox {
                padding: 8px;
                border: 1px solid #ced4da;
                border-radius: 4px;
                background-color: white;
                min-width: 120px;
            }
            QComboBox:focus {
                border-color: #007bff;
            }
        """)
        form_layout.addRow("화면 갱신 주기:", self.display_combo)
        
        # 저장 주기 설정
        self.save_combo = QComboBox()
        self.save_combo.addItems(AppSettings.SAVE_INTERVAL_LABELS)
        self.save_combo.setStyleSheet("""
            QComboBox {
                padding: 8px;
                border: 1px solid #ced4da;
                border-radius: 4px;
                background-color: white;
                min-width: 120px;
            }
            QComboBox:focus {
                border-color: #007bff;
            }
        """)
        form_layout.addRow("데이터베이스 저장 주기:", self.save_combo)
        
        # 현재 설정값 로드
        self._load_current_values()
        
        layout.addLayout(form_layout)
        
        # 정보 영역
        info_layout = QVBoxLayout()
        info_layout.setSpacing(8)
        
        info_title = QLabel("설정 정보")
        info_title.setFont(QFont("Arial", 12, QFont.Bold))
        info_title.setStyleSheet("color: #495057; margin-top: 20px; margin-bottom: 10px;")
        info_layout.addWidget(info_title)
        
        detail_label = QLabel("""
- 통신 주기: RSD와 센서 데이터를 주고받는 통신 간격
- 화면 갱신 주기: RSD 센서 데이터를 화면에 표시하는 간격
- 데이터베이스 저장 주기: 수집된 데이터를 DB에 저장하는 간격
- RSD별 개별 갱신: 각 RSD 통신 완료시 즉시 화면 갱신
- 설정 변경사항은 다음 모니터링 시작시 적용됩니다
        """)
        detail_label.setStyleSheet("""
            background-color: #f8f9fa; 
            padding: 12px; 
            border-radius: 6px;
            border-left: 4px solid #007bff;
        """)
        detail_label.setWordWrap(True)
        info_layout.addWidget(detail_label)
        
        layout.addLayout(info_layout)
        
        # 버튼
        button_box = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel,
            self
        )
        button_box.setStyleSheet("""
            QPushButton {
                padding: 8px 20px;
                border-radius: 6px;
                font-weight: bold;
                font-size: 11px;
            }
            QPushButton[text="OK"] {
                background-color: #007bff;
                color: white;
                border: none;
            }
            QPushButton[text="OK"]:hover {
                background-color: #0056b3;
            }
            QPushButton[text="Cancel"] {
                background-color: #6c757d;
                color: white;
                border: none;
            }
            QPushButton[text="Cancel"]:hover {
                background-color: #545b62;
            }
        """)
        
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)
        
    def _load_current_values(self):
        """현재 설정값으로 콤보박스 초기화"""
        # 통신 간격 매핑
        communication_mapping = {value: index for index, value in enumerate(AppSettings.COMMUNICATION_INTERVALS)}
        communication_index = communication_mapping.get(self.config_manager.monitoring_communication_interval, 1)
        self.communication_combo.setCurrentIndex(communication_index)
        
        # 표시 주기 매핑
        display_mapping = {value: index for index, value in enumerate(AppSettings.DISPLAY_INTERVALS)}
        display_index = display_mapping.get(self.config_manager.monitoring_display_interval, 1)
        self.display_combo.setCurrentIndex(display_index)
        
        # 저장 주기 매핑
        save_mapping = {value: index for index, value in enumerate(AppSettings.SAVE_INTERVALS)}
        save_index = save_mapping.get(self.config_manager.monitoring_save_interval, 1)
        self.save_combo.setCurrentIndex(save_index)

    def get_updated_values(self) -> tuple:
        """설정 다이얼로그에서 설정된 값 반환"""
        # 통신 간격 변환 (새로 추가)
        communication_interval = AppSettings.COMMUNICATION_INTERVALS[self.communication_combo.currentIndex()]
        
        # 표시 주기 변환
        display_interval = AppSettings.DISPLAY_INTERVALS[self.display_combo.currentIndex()]
        
        # 저장 주기 변환
        save_interval = AppSettings.SAVE_INTERVALS[self.save_combo.currentIndex()]
        
        return (communication_interval, display_interval, save_interval, self.config_manager.monitoring_rsd_communication_delay)


# =============================================================================
# 모니터링 스레드 클래스
# =============================================================================

class MonitoringThread(QThread):
    """RSD 통신 데이터 수집 스레드 - 완전 클래스 기반, LogManager 의존성 주입"""
    data_updated = Signal(list)
    single_rsd_updated = Signal(object)
    status_updated = Signal(str)
    error_occurred = Signal(str)
    initialization_progress = Signal(str, str)
    backup_finished = Signal(str)
    
    def __init__(self, config_manager: ConfigManager):
        super().__init__()
        self.config_manager = config_manager
        self.is_running = False
        self.is_initializing = False
        
        # 백엔드 서비스들
        self.db_manager = None
        self.db_connection = None
        self.communication_manager = None
        
        # 이벤트 루프 관리용 변수 추가
        self._event_loop = None
        self._shutdown_complete = False
        
        # 저장 주기 관리를 위한 새로운 변수들 추가
        self._sensor_data_buffer = []  # 데이터 버퍼
        self._last_save_time = None    # 마지막 저장 시간
        self._save_task = None         # 저장 태스크
        
        # LogManager 의존성 주입 방식으로 변경
        self.log_manager = None
        if LOGGING_AVAILABLE:
            self.log_manager = LogManager(config_manager)
            logger.info("LogManager 의존성 주입 완료")

    def run_final_save_blocking(self):
        """
        동기 컨텍스트에서 최종 저장 로직을 실행하기 위한 블로킹 메서드.
        스레드가 시작되어 manager들이 초기화되었다고 가정합니다.
        """
        buffer_count = len(self._sensor_data_buffer) if hasattr(self, '_sensor_data_buffer') else 0
        if buffer_count == 0:
            return

        # 저장을 위한 의존성(manager)들이 준비되었는지 확인
        if not all(hasattr(self, mgr) and getattr(self, mgr) for mgr in ['db_manager', 'communication_manager']):
            if self.log_manager:
                self.log_manager.error_log("최종저장", "저장에 필요한 관리자 객체가 초기화되지 않아 저장할 수 없습니다.")
            return
        
        if self.log_manager:
            self.log_manager.operation_log("시스템", f"프로그램 종료 전 최종 데이터 저장 시작. (대상: {buffer_count}개)")

        # 새 이벤트 루프를 사용하여 비동기 저장 실행
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(self._final_data_save())
        finally:
            loop.close()
            asyncio.set_event_loop(None)

    async def _save_data_with_retry_and_backup(self, data_to_save: List[RSDSensorData]):
        """
        데이터를 DB에 저장하되, 실패 시 재시도하고 최종 실패 시 CSV로 백업합니다.
        성공 시 백업된 로그 복구를 시도합니다.
        """
        if not data_to_save:
            return

        max_retries = 2
        total_attempts = 1 + max_retries
        success = False

        for attempt in range(total_attempts):
            try:
                if self.log_manager:
                    self.log_manager.operation_log("데이터저장", 
                        f"DB 저장 시도 #{attempt + 1}/{total_attempts} (대상: {len(data_to_save)}개)")

                saved_count = await self.communication_manager.save_collected_data(data_to_save)
                
                if saved_count > 0:
                    self._sensor_data_buffer.clear()
                    self._last_save_time = datetime.now()
                    success = True
                    if self.log_manager:
                        self.log_manager.operation_log("데이터저장", f"DB 저장 성공: {saved_count}개")
                    
                    # DB 연결 복구 확인 -> 백업된 로그 처리 시도
                    await self._process_log_backups_if_any()
                    
                    break
                else:
                    if self.log_manager:
                        self.log_manager.error_log("데이터저장", f"시도 #{attempt + 1} 실패: 저장된 데이터 0개")

            except Exception as e:
                if self.log_manager:
                    self.log_manager.error_log("데이터저장", f"시도 #{attempt + 1} 중 예외 발생: {e}")
            
            if attempt < max_retries:
                await asyncio.sleep(1.0)

        if not success:
            if self.log_manager:
                self.log_manager.error_log("데이터저장", 
                    f"총 {total_attempts}회 DB 저장 실패. CSV 백업을 시작합니다.")

            file_path = self.db_manager.backup_data_to_csv(data_to_save)
            if file_path:
                self.backup_finished.emit(file_path)
                self._sensor_data_buffer.clear()
            else:
                if self.log_manager:
                    self.log_manager.error_log("데이터저장", "치명적 오류: CSV 백업마저 실패했습니다. 데이터가 유실될 수 있습니다.")

    async def _process_log_backups_if_any(self):
        """
        백업된 로그 파일이 있는지 확인하고 처리를 시도합니다.
        """
        if not self.db_manager:
            return

        backup_dir = "backup_logs"
        if not (os.path.exists(backup_dir) and any(f.endswith('.csv') for f in os.listdir(backup_dir))):
            return # 처리할 파일이 없으면 조용히 종료

        try:
            if self.log_manager:
                self.log_manager.operation_log("로그복구", "DB 연결 복구 감지, 백업된 로그 복구를 시작합니다.")

            result = await self.db_manager.process_pending_log_backups()

            if result and result['processed'] > 0:
                log_msg = f"로그 백업 처리 완료: {result['success']}개 파일 성공, {result['failed']}개 실패."
                if self.log_manager:
                    self.log_manager.operation_log("로그복구", log_msg)
                # 메인 윈도우에 간단한 알림을 줄 수 있습니다.
                self.status_updated.emit(log_msg)

        except Exception as e:
            if self.log_manager:
                self.log_manager.error_log("로그복구", f"백업된 로그 처리 중 예상치 못한 오류 발생: {e}")

    def _force_emergency_save(self):
        """긴급 강제 저장 플래그 설정"""
        self._emergency_save_requested = True
        if self.log_manager:
            buffer_count = len(self._sensor_data_buffer)
            self.log_manager.operation_log("긴급저장", 
                f"긴급 저장 요청됨 - 대상: {buffer_count}개 데이터")

    async def _check_emergency_save(self):
        """긴급 저장 요청 체크 및 실행"""
        if hasattr(self, '_emergency_save_requested') and self._emergency_save_requested:
            self._emergency_save_requested = False
            
            if self._sensor_data_buffer:
                try:
                    buffer_count = len(self._sensor_data_buffer)
                    if self.log_manager:
                        self.log_manager.operation_log("긴급저장", 
                            f"긴급 저장 요청 처리 시작: {buffer_count}개")
                    
                    start_time = datetime.now()
                    await self._save_buffered_data()
                    end_time = datetime.now()
                    
                    duration = (end_time - start_time).total_seconds()
                    remaining = len(self._sensor_data_buffer)
                    saved = buffer_count - remaining
                    
                    if self.log_manager:
                        if remaining == 0:
                            self.log_manager.operation_log("긴급저장", 
                                f"긴급 저장 완료: {saved}개 저장 (소요: {duration:.2f}초)")
                        else:
                            self.log_manager.operation_log("긴급저장", 
                                f"긴급 저장 부분 완료: {saved}개 저장, {remaining}개 남음 (소요: {duration:.2f}초)")
                
                except Exception as e:
                    if self.log_manager:
                        self.log_manager.error_log("긴급저장", f"긴급 저장 실패: {str(e)}")
            else:
                if self.log_manager:
                    self.log_manager.operation_log("긴급저장", "긴급 저장 요청 - 저장할 데이터 없음")

    def get_buffer_status(self):
        """현재 버퍼 상태 반환 (외부에서 확인용)"""
        return {
            'buffer_count': len(self._sensor_data_buffer),
            'last_save_time': self._last_save_time,
            'emergency_save_requested': getattr(self, '_emergency_save_requested', False)
        }

   
    def run(self):
        """스레드 실행"""
        self.is_running = True
        self._shutdown_complete = False
        
        # 새로운 이벤트 루프 생성 및 설정
        self._event_loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._event_loop)
        
        try:
            self._event_loop.run_until_complete(self._async_monitoring_loop())
        except Exception as e:
            self.error_occurred.emit(f"모니터링 오류: {str(e)}")
            if self.log_manager:
                self.log_manager.error_log("스레드", f"스레드 실행 오류: {str(e)}")
        finally:
            # 이벤트 루프 완전 종료 처리
            self._complete_shutdown()

    async def _async_monitoring_loop(self):
        """비동기 모니터링 루프 - monitoring_communication_interval 사용"""
        try:
            # 1. 시스템 초기화
            self.is_initializing = True
            
            if not await self._initialize_system():
                self.is_initializing = False
                self.error_occurred.emit("시스템 초기화 실패")
                return
            
            self.is_initializing = False
            cycle_count = 0
            
            # 저장 주기 관리를 위한 변수 초기화
            self._sensor_data_buffer.clear()
            self._last_save_time = datetime.now()
            
            if self.log_manager:
                self.log_manager.operation_log("모니터링", "모니터링 루프 시작")
                self.log_manager.operation_log("설정", 
                    f"통신 주기: {self.config_manager.monitoring_communication_interval}초, "
                    f"화면 갱신 주기: {self.config_manager.monitoring_display_interval}초, "
                    f"DB 저장 주기: {self.config_manager.monitoring_save_interval}초")
            
            # 2. 저장 주기 타이머 시작 (별도 태스크로 실행)
            self._save_task = asyncio.create_task(self._database_save_scheduler())
            
            # 3. 실시간 모니터링 루프 (통신 주기 기반)
            while self.is_running:
                cycle_count += 1
                
                try:
                    if not self.is_running:
                        break
                    
                    # 센서 데이터 수집
                    sensor_data_list = await self.communication_manager.collect_all_data()
                    
                    if sensor_data_list:
                        # 개별 RSD 데이터 즉시 UI 업데이트
                        for sensor_data in sensor_data_list:
                            if not self.is_running:
                                break
                            self.single_rsd_updated.emit(sensor_data)
                        
                        # 데이터를 버퍼에 추가 (저장은 별도 스케줄러에서 처리)
                        self._add_to_buffer(sensor_data_list)
                    
                    # 상태 업데이트
                    if cycle_count % 10 == 0:  # 10 사이클마다 상태 업데이트
                        stats = self.communication_manager.get_statistics()
                        buffer_size = len(self._sensor_data_buffer)
                        last_save_info = self._get_last_save_info()
                        self.status_updated.emit(
                            f"모니터링 중... (사이클 {cycle_count}, 성공률 {stats['success_rate']:.1f}%, "
                            f"대기 데이터 {buffer_size}개, {last_save_info})"
                        )
                    
                    # 통신 주기만큼 대기
                    for _ in range(self.config_manager.monitoring_communication_interval * 10):
                        if not self.is_running:
                            break
                        await asyncio.sleep(0.1)
                    
                except asyncio.CancelledError:
                    if self.log_manager:
                        self.log_manager.operation_log("모니터링", "모니터링 태스크 취소됨")
                    break
                except Exception as e:
                    if self.log_manager:
                        self.log_manager.error_log("모니터링", f"모니터링 루프 오류: {str(e)}")
                    # 오류 발생 시 잠시 대기 후 재시도
                    await asyncio.sleep(1.0)
            
            if self.log_manager:
                self.log_manager.operation_log("모니터링", "모니터링 루프 종료")
        
        except Exception as e:
            self.error_occurred.emit(f"모니터링 루프 오류: {str(e)}")
            if self.log_manager:
                self.log_manager.error_log("모니터링", f"모니터링 루프 치명적 오류: {str(e)}")
        finally:
            # 종료 처리 시작
            if self.log_manager:
                buffer_count = len(self._sensor_data_buffer)
                self.log_manager.operation_log("종료", 
                    f"모니터링 종료 처리 시작 - 남은 버퍼 데이터: {buffer_count}개")
            
            # 1. 저장 스케줄러 태스크 중지
            if self._save_task and not self._save_task.done():
                if self.log_manager:
                    self.log_manager.operation_log("종료", "저장 스케줄러 태스크 취소 중...")
                self._save_task.cancel()
                try:
                    await self._save_task
                except asyncio.CancelledError:
                    if self.log_manager:
                        self.log_manager.operation_log("종료", "저장 스케줄러 태스크 취소 완료")
            
            # 2. 남은 버퍼 데이터 최종 저장 (중요!)
            try:
                await self._final_data_save()
            except Exception as e:
                if self.log_manager:
                    self.log_manager.error_log("종료", f"최종 데이터 저장 중 오류: {str(e)}")
            
            # 3. 종료 완료 로그
            if self.log_manager:
                self.log_manager.operation_log("종료", "모니터링 루프 종료 처리 완료")

    async def _database_save_scheduler(self):
        """데이터베이스 저장 스케줄러 - 절대 시간 기준으로 정확한 주기 관리"""
        try:
            save_interval = self.config_manager.monitoring_save_interval
            
            if self.log_manager:
                self.log_manager.operation_log("저장", f"DB 저장 스케줄러 시작 (주기: {save_interval}초)")
            
            # 다음 저장 예정 시간 계산 (현재 시간 + 저장 주기)
            next_save_time = datetime.now() + timedelta(seconds=save_interval)
            
            if self.log_manager:
                self.log_manager.operation_log("저장", 
                    f"첫 번째 저장 예정 시간: {next_save_time.strftime('%H:%M:%S')}")
            
            while self.is_running:
                try:
                    current_time = datetime.now()
                    
                    # 저장 시간이 되었는지 확인
                    if current_time >= next_save_time:
                        if self.log_manager:
                            delay = (current_time - next_save_time).total_seconds()
                            self.log_manager.operation_log("저장", 
                                f"저장 시간 도달: 예정 {next_save_time.strftime('%H:%M:%S')}, "
                                f"실제 {current_time.strftime('%H:%M:%S')} "
                                f"(지연: {delay:.1f}초)")
                        
                        # 버퍼 상태 확인 및 로그
                        buffer_size = len(self._sensor_data_buffer)
                        if self.log_manager:
                            self.log_manager.operation_log("저장", 
                                f"저장 시작: 버퍼 데이터 {buffer_size}개")
                        
                        # 데이터가 있을 때만 저장
                        if self._sensor_data_buffer:
                            # 신규 저장 메서드 호출
                            await self._save_data_with_retry_and_backup(self._sensor_data_buffer.copy())
                        else:
                            if self.log_manager:
                                self.log_manager.operation_log("저장", 
                                    "저장 건너뜀: 버퍼에 데이터 없음")
                        
                        # 다음 저장 시간 계산 (절대 시간 기준)
                        next_save_time = next_save_time + timedelta(seconds=save_interval)
                        
                        # 만약 이미 다음 저장 시간도 지났다면, 현재 시간 기준으로 재계산
                        current_time_after_save = datetime.now()
                        if next_save_time <= current_time_after_save:
                            # 지연이 심한 경우 현재 시간 기준으로 다시 계산
                            skip_count = int((current_time_after_save - next_save_time).total_seconds() / save_interval) + 1
                            next_save_time = next_save_time + timedelta(seconds=save_interval * skip_count)
                            
                            if self.log_manager:
                                self.log_manager.operation_log("저장", 
                                    f"지연으로 인한 저장 시간 재조정: {skip_count}번 건너뛰어 "
                                    f"다음 저장 {next_save_time.strftime('%H:%M:%S')}")
                        
                        if self.log_manager:
                            remaining_time = (next_save_time - current_time_after_save).total_seconds()
                            self.log_manager.operation_log("저장", 
                                f"다음 저장 예정: {next_save_time.strftime('%H:%M:%S')} "
                                f"({remaining_time:.0f}초 후)")
                    
                    # 짧은 간격으로 대기 (100ms)
                    await asyncio.sleep(0.1)
                    
                except asyncio.CancelledError:
                    if self.log_manager:
                        self.log_manager.operation_log("저장", "저장 스케줄러 취소됨")
                    break
                except Exception as e:
                    if self.log_manager:
                        self.log_manager.error_log("저장", f"저장 스케줄러 오류: {str(e)}")
                    await asyncio.sleep(1.0)
                    
        except Exception as e:
            if self.log_manager:
                self.log_manager.error_log("저장", f"저장 스케줄러 실행 오류: {str(e)}")
    
    def _add_to_buffer(self, sensor_data_list):
        """센서 데이터를 버퍼에 추가 - 디버그 로그 추가"""
        old_buffer_size = len(self._sensor_data_buffer)
        self._sensor_data_buffer.extend(sensor_data_list)
        new_buffer_size = len(self._sensor_data_buffer)
        
        # 주기적으로 버퍼 상태 로그 (100개 단위)
        if new_buffer_size % 100 == 0 and self.log_manager:
            save_interval = self.config_manager.monitoring_save_interval
            estimated_save_time = None
            if self._last_save_time:
                next_estimated = self._last_save_time + timedelta(seconds=save_interval)
                remaining = (next_estimated - datetime.now()).total_seconds()
                estimated_save_time = f"{remaining:.0f}초 후"
            else:
                estimated_save_time = "미정"
                
            self.log_manager.operation_log("버퍼", 
                f"버퍼 상태: {new_buffer_size}개 (추가: {len(sensor_data_list)}개), "
                f"다음 저장 예상: {estimated_save_time}")
        
        # 버퍼 크기 제한 (메모리 보호)
        max_buffer_size = 10000  # 최대 10,000개 데이터
        if len(self._sensor_data_buffer) > max_buffer_size:
            # 오래된 데이터부터 제거
            excess_count = len(self._sensor_data_buffer) - max_buffer_size
            self._sensor_data_buffer = self._sensor_data_buffer[excess_count:]
            
            if self.log_manager:
                self.log_manager.operation_log("버퍼", 
                    f"버퍼 크기 초과로 {excess_count}개 데이터 제거")


    async def _save_buffered_data(self):
        """버퍼에 있는 데이터를 데이터베이스에 저장 - 디버그 로그 추가"""
        if not self._sensor_data_buffer:
            return
        
        data_to_save = self._sensor_data_buffer.copy()
        data_count = len(data_to_save)
        
        try:
            if self.log_manager:
                self.log_manager.operation_log("데이터저장", 
                    f"저장 시작: {data_count}개 데이터 처리")
            
            # 배치 저장 실행 - save_collected_data 메서드 사용
            save_start_time = datetime.now()
            saved_count = await self.communication_manager.save_collected_data(data_to_save)
            save_end_time = datetime.now()
            
            save_duration = (save_end_time - save_start_time).total_seconds()
            
            if saved_count > 0:
                # 저장 성공한 만큼 버퍼에서 제거
                self._sensor_data_buffer.clear()
                self._last_save_time = datetime.now()
                
                if self.log_manager:
                    self.log_manager.operation_log("데이터저장", 
                        f"데이터 저장 성공: {saved_count}개")
                    self.log_manager.operation_log("저장", 
                        f"DB 저장 완료: {saved_count}/{data_count}개 데이터 (소요: {save_duration:.2f}초)")
            else:
                if self.log_manager:
                    self.log_manager.error_log("데이터저장", 
                        f"데이터 저장 실패: {data_count}개 (소요: {save_duration:.2f}초)")
                    self.log_manager.error_log("저장", "데이터 저장 실패")
                    
        except Exception as e:
            if self.log_manager:
                self.log_manager.error_log("저장", f"버퍼 데이터 저장 중 오류: {str(e)}")

    async def _final_data_save(self):
        """프로그램 종료 시 남은 데이터 최종 저장 - 개선된 버전"""
        buffer_count = len(self._sensor_data_buffer)
        
        if self.log_manager:
            self.log_manager.operation_log("최종저장", 
                f"최종 데이터 저장 시작 - 대상: {buffer_count}개")
        
        if buffer_count == 0:
            if self.log_manager:
                self.log_manager.operation_log("최종저장", "저장할 데이터 없음 - 최종 저장 완료")
            return
        
        # 최종 저장 실행
        await self._save_data_with_retry_and_backup(self._sensor_data_buffer.copy())

        # 최종 상태 로그
        final_buffer_count = len(self._sensor_data_buffer)
        if self.log_manager:
            if final_buffer_count == 0:
                self.log_manager.operation_log("최종저장", "모든 데이터 저장/백업 완료 - 데이터 손실 없음")
            else:
                self.log_manager.error_log("최종저장", 
                    f"최종 저장 실패 후 백업에도 실패하여 저장되지 않은 데이터 {final_buffer_count}개 - 주의 필요")
                

    def _get_last_save_info(self):
        """마지막 저장 시간 정보 반환 - 더 상세한 정보 제공"""
        if self._last_save_time:
            elapsed = (datetime.now() - self._last_save_time).total_seconds()
            save_interval = self.config_manager.monitoring_save_interval
            progress = (elapsed / save_interval) * 100 if save_interval > 0 else 0
            
            return f"마지막 저장: {elapsed:.0f}초 전 ({progress:.0f}%)"
        else:
            return "아직 저장 안됨"

    
    async def _initialize_system(self) -> bool:
        """시스템 초기화 - 연결 테스트와 실제 통신 분리"""
        try:
            self.initialization_progress.emit(
                "시스템 초기화 중...",
                "데이터베이스 연결을 설정하고 있습니다..."
            )

            # 1. 데이터베이스 연결 초기화
            db_config = DatabaseConfig(
                host=self.config_manager.database_host,
                port=self.config_manager.database_port,
                database=self.config_manager.database_name,
                username=self.config_manager.database_username,
                password=self.config_manager.database_password
            )

            # DatabaseManager 사용 (내부에서 생성)
            self.db_manager = DatabaseManager(db_config)
            # DB 재연결 콜백 등록
            self.db_manager.set_status_callback(self._handle_db_reconnection)

            if not await self.db_manager.initialize():
                return False

            # 연결 테스트
            if not await self.db_manager.test_connection():
                return False

            # 2. 연결 테스트 수행
            self.initialization_progress.emit(
                "기기 연결 테스트 중...",
                "RSD 기기들과의 연결을 테스트하고 있습니다..."
            )

            from set_string import StringManager, RSDManager, RSDTestManager

            string_manager = StringManager()
            rsd_manager = RSDManager()
            string_manager.set_device_repository(self.db_manager.get_device_repository())
            rsd_manager.set_device_repository(self.db_manager.get_device_repository())

            alert_repo = self.db_manager.get_alert_repository()
            test_manager = RSDTestManager(self.config_manager, alert_repository=alert_repo)
            test_results = await test_manager.test_all_strings(string_manager, rsd_manager)

            active_strings = []
            active_devices = []

            for string_id, string_results in test_results.items():
                string_info = await string_manager.get_string_by_id(string_id)
                if not string_info:
                    continue

                successful_rsds = []
                for result in string_results:
                    if result.is_success:
                        rsd_info = await rsd_manager.get_rsd_by_id(string_id, result.rsd_id)
                        if rsd_info:
                            successful_rsds.append(rsd_info)

                if successful_rsds:
                    active_strings.append(string_info)
                    active_devices.extend(successful_rsds)
                    if self.log_manager:
                        self.log_manager.operation_log("연결테스트", f"String {string_id} 연결 테스트 완료: {len(successful_rsds)}개 RSD 활성화")

            if not active_strings:
                if self.log_manager:
                    self.log_manager.error_log("시스템", "활성화된 RSD 기기가 없어 모니터링을 시작할 수 없습니다.")
                if self.db_manager and self.db_manager.is_initialized():
                    if alert_repo:
                        await alert_repo.save_system_error_alert(
                            component="System",
                            error_message="활성화된 RSD 기기 없음"
                        )
                return False

            # 3. 통신 관리자 초기화
            self.initialization_progress.emit(
                "통신 시스템 초기화 중...",
                "실제 데이터 수집 시스템을 준비하고 있습니다..."
            )

            from communication import CommunicationManager

            self.communication_manager = CommunicationManager(self.config_manager, self.db_manager, self.log_manager)

            if not await self.communication_manager.initialize():
                return False

            # 4. 연결 테스트 결과를 통신 관리자에 전달
            self.communication_manager.set_active_devices(active_strings, active_devices)

            self.initialization_progress.emit(
                "초기화 완료",
                "모니터링을 시작합니다..."
            )

            if self.log_manager:
                self.log_manager.operation_log("시스템", "시스템 초기화 완료")

            return True

        except Exception as e:
            error_msg = f"시스템 초기화 실패: {str(e)}"
            if self.log_manager:
                self.log_manager.error_log("시스템", error_msg)
            if self.db_manager and self.db_manager.is_initialized():
                alert_repo = self.db_manager.get_alert_repository()
                if alert_repo:
                    await alert_repo.save_system_error_alert(
                        component="SystemInitialize",
                        error_message=str(e)
                    )
            return False

    
    async def _handle_db_reconnection(self):
        """DB 재연결 시 호출될 콜백 함수. 백업 데이터 처리를 담당합니다."""
        logger.info("DB 재연결 콜백 수신. 백업된 데이터 처리를 시작합니다.")
        try:
            if self.db_manager:
                if self.db_manager.sensor_repository:
                    await self.db_manager.sensor_repository.process_pending_backups()
                if self.db_manager.alert_repository:
                    await self.db_manager.alert_repository.process_pending_log_backups()
                logger.info("백업 데이터 처리 완료.")
            else:
                logger.warning("DB 매니저가 초기화되지 않아 백업을 처리할 수 없습니다.")
        except Exception as e:
            logger.error(f"백업 데이터 처리 중 오류 발생: {e}")

    async def _cleanup_resources(self):
        """리소스 정리 작업 - 향상된 정리 로직"""
        try:
            if self.log_manager:
                self.log_manager.operation_log("시스템", "리소스 정리 시작")
            
            # 1. 통신 관리자 정리
            if hasattr(self, 'communication_manager') and self.communication_manager:
                try:
                    if hasattr(self.communication_manager, 'close_all_connections'):
                        await self.communication_manager.close_all_connections()
                    self.communication_manager.reset_statistics()
                    self.communication_manager = None
                except Exception as e:
                    if self.log_manager:
                        self.log_manager.error_log("시스템", f"통신 관리자 정리 중 오류: {e}")
            
            # 2. 데이터베이스 연결 정리
            if hasattr(self, 'db_manager') and self.db_manager:
                try:
                    await self.db_manager.close()
                    self.db_manager = None
                except Exception as e:
                    if self.log_manager:
                        self.log_manager.error_log("시스템", f"DB 관리자 정리 중 오류: {e}")
            
            # 3. 기존 방식 호환성 유지
            if hasattr(self, 'db_connection') and self.db_connection:
                try:
                    await self.db_connection.disconnect()
                    self.db_connection = None
                except Exception as e:
                    if self.log_manager:
                        self.log_manager.error_log("시스템", f"DB 연결 정리 중 오류: {e}")
            
            if self.log_manager:
                self.log_manager.operation_log("시스템", "리소스 정리 완료")
            
        except Exception as e:
            if self.log_manager:
                self.log_manager.error_log("시스템", f"리소스 정리 중 오류: {e}")

    def _complete_shutdown(self):
        """이벤트 루프 완전 종료 처리 - 데이터 보존 우선"""
        if self._shutdown_complete:
            return
        
        try:
            if self.log_manager:
                buffer_count = len(self._sensor_data_buffer) if hasattr(self, '_sensor_data_buffer') else 0
                self.log_manager.operation_log("시스템", 
                    f"완전 종료 처리 시작 - 현재 버퍼: {buffer_count}개")
            
            if self._event_loop and not self._event_loop.is_closed():
                # 1. 남은 데이터 긴급 저장 (이벤트 루프 종료 전)
                try:
                    if (hasattr(self, '_sensor_data_buffer') and 
                        self._sensor_data_buffer and 
                        hasattr(self, 'communication_manager') and 
                        self.communication_manager):
                        
                        if self.log_manager:
                            self.log_manager.operation_log("시스템", 
                                "이벤트 루프 종료 전 긴급 데이터 저장 시도...")
                        
                        # 최종 저장 실행
                        emergency_save_task = self._event_loop.create_task(
                            self._emergency_final_save()
                        )
                        
                        # 5초 내에 완료되도록 대기
                        try:
                            self._event_loop.run_until_complete(
                                asyncio.wait_for(emergency_save_task, timeout=5.0)
                            )
                            
                            if self.log_manager:
                                remaining = len(self._sensor_data_buffer) if hasattr(self, '_sensor_data_buffer') else 0
                                self.log_manager.operation_log("시스템", 
                                    f"긴급 저장 완료 - 남은 데이터: {remaining}개")
                        
                        except asyncio.TimeoutError:
                            if self.log_manager:
                                self.log_manager.error_log("시스템", 
                                    "긴급 저장 시간 초과 (5초) - 일부 데이터 유실 가능")
                        
                        except Exception as e:
                            if self.log_manager:
                                self.log_manager.error_log("시스템", 
                                    f"긴급 저장 중 오류: {str(e)}")
                
                except Exception as e:
                    if self.log_manager:
                        self.log_manager.error_log("시스템", 
                            f"긴급 저장 설정 중 오류: {str(e)}")
                
                # 2. 열린 연결들 강제 종료
                try:
                    # 이벤트 루프의 모든 연결 종료
                    self._event_loop.run_until_complete(self._force_close_connections())
                except Exception as e:
                    if self.log_manager:
                        self.log_manager.error_log("시스템", f"연결 강제 종료 중 오류: {e}")
                
                # 3. 이벤트 루프 완전 종료
                try:
                    # 남은 콜백들 실행
                    self._event_loop.run_until_complete(asyncio.sleep(0.1))
                    
                    # 이벤트 루프 중지 및 종료
                    self._event_loop.stop()
                    
                    # 약간의 지연 후 완전 종료
                    import time
                    time.sleep(0.1)
                    
                    self._event_loop.close()
                    
                    if self.log_manager:
                        self.log_manager.operation_log("시스템", "이벤트 루프 완전 종료 완료")
                        
                except Exception as e:
                    if self.log_manager:
                        self.log_manager.error_log("시스템", f"이벤트 루프 종료 중 오류: {e}")
            
            self._event_loop = None
            self._shutdown_complete = True
            self.is_running = False
            
            # 최종 상태 리포트
            if self.log_manager:
                final_buffer_count = len(self._sensor_data_buffer) if hasattr(self, '_sensor_data_buffer') else 0
                if final_buffer_count == 0:
                    self.log_manager.operation_log("시스템", 
                        "완전 종료 성공 - 모든 데이터 안전하게 처리됨")
                else:
                    self.log_manager.operation_log("시스템", 
                        f"완전 종료 완료 - 주의: {final_buffer_count}개 데이터 처리되지 않음")
            
        except Exception as e:
            if self.log_manager:
                self.log_manager.error_log("시스템", f"완전 종료 처리 중 예외: {e}")
            self._shutdown_complete = True
            self.is_running = False

    async def _emergency_final_save(self):
        """긴급 최종 저장 - 이벤트 루프 종료 전 실행"""
        if not self._sensor_data_buffer:
            return
        
        await self._save_data_with_retry_and_backup(self._sensor_data_buffer.copy())

    async def _force_close_connections(self):
        """열린 모든 연결 강제 종료"""
        try:
            # 통신 관리자의 연결 종료
            if hasattr(self, 'communication_manager') and self.communication_manager:
                if hasattr(self.communication_manager, 'close_all_connections'):
                    await self.communication_manager.close_all_connections()
            
            # 데이터베이스 연결 종료
            if hasattr(self, 'db_manager') and self.db_manager:
                await self.db_manager.close()
            
            # 기존 방식 호환성 유지
            if hasattr(self, 'db_connection') and self.db_connection:
                await self.db_connection.disconnect()
                
        except Exception as e:
            if self.log_manager:
                self.log_manager.error_log("시스템", f"연결 강제 종료 중 오류: {e}")

    def stop(self):
        """스레드 중단 - 최종 데이터 저장 보장"""
        if self.log_manager:
            buffer_count = len(self._sensor_data_buffer) if hasattr(self, '_sensor_data_buffer') else 0
            self.log_manager.operation_log("시스템", 
                f"모니터링 스레드 중단 요청 - 현재 버퍼: {buffer_count}개 데이터")
        
        # 실행 플래그만 중지하여 스레드가 스스로 종료되도록 유도합니다.
        # 메인 스레드를 차단하는 wait() 호출을 제거합니다.
        self.is_running = False
        self.is_initializing = False

    async def force_save_debug(self):
        """강제 저장 및 디버그 정보 출력"""
        if not self.log_manager:
            return
            
        self.log_manager.operation_log("디버그", "=== 강제 저장 시작 ===")
        
        before_time = datetime.now()
        buffer_size_before = len(self._sensor_data_buffer)
        
        if buffer_size_before > 0:
            await self._save_buffered_data()
            
            after_time = datetime.now()
            duration = (after_time - before_time).total_seconds()
            buffer_size_after = len(self._sensor_data_buffer)
            
            self.log_manager.operation_log("디버그", 
                f"강제 저장 완료: {buffer_size_before}개 → {buffer_size_after}개, "
                f"소요시간: {duration:.2f}초")
        else:
            self.log_manager.operation_log("디버그", "강제 저장 건너뜀: 버퍼 비어있음")
        
        self.log_manager.operation_log("디버그", "===================")

    def get_save_timing_info(self):
        """저장 타이밍 정보 반환 (UI 표시용)"""
        current_time = datetime.now()
        save_interval = self.config_manager.monitoring_save_interval
        buffer_size = len(self._sensor_data_buffer)
        
        info = {
            'current_time': current_time.strftime('%H:%M:%S'),
            'save_interval': save_interval,
            'buffer_size': buffer_size,
            'last_save_time': None,
            'elapsed_since_save': None,
            'progress_percent': 0,
            'estimated_next_save': None
        }
        
        if self._last_save_time:
            elapsed = (current_time - self._last_save_time).total_seconds()
            progress = (elapsed / save_interval) * 100 if save_interval > 0 else 0
            next_save = self._last_save_time + timedelta(seconds=save_interval)
            
            info.update({
                'last_save_time': self._last_save_time.strftime('%H:%M:%S'),
                'elapsed_since_save': elapsed,
                'progress_percent': min(progress, 100),
                'estimated_next_save': next_save.strftime('%H:%M:%S')
            })
        
        return info

    # 모니터링 루프에서 주기적으로 디버그 정보 출력하는 메서드 추가
    async def _periodic_debug_output(self):
        """주기적으로 저장 스케줄러 디버그 정보 출력 (개발/디버그용)"""
        debug_count = 0
        while self.is_running:
            try:
                # 1분마다 디버그 정보 출력
                await asyncio.sleep(60)
                debug_count += 1
                
                if self.log_manager:
                    self.log_manager.operation_log("디버그", 
                        f"=== 주기적 상태 체크 #{debug_count} ===")
                    
                    # 저장 스케줄러 상태 출력
                    self.debug_save_scheduler_status()
                    
                    # 통신 상태도 함께 출력
                    if hasattr(self, 'communication_manager') and self.communication_manager:
                        stats = self.communication_manager.get_statistics()
                        self.log_manager.operation_log("디버그", 
                            f"통신 통계: 성공률 {stats['success_rate']:.1f}%, "
                            f"총 시도 {stats['total_attempts']}회")
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                if self.log_manager:
                    self.log_manager.error_log("디버그", f"주기적 디버그 오류: {str(e)}")
                await asyncio.sleep(5)

                
# =============================================================================
# 메인 윈도우 클래스
# =============================================================================

class RSDMonitoringMainWindow(QMainWindow):
    """RSD 모니터링 메인 윈도우"""
    
    def __init__(self):
        super().__init__()
        self.monitoring_thread = None
        self.string_widgets = {}
        self.total_rsd_count = 0
        self.total_string_count = 0
        self.is_exiting = False
        self.is_initializing = False
        
        # ConfigManager 직접 사용
        self.config_manager = ConfigManager()
        
        # 백업 처리용 DB 매니저 초기화. 실제 연결은 필요할 때 수행합니다.
        db_config = self.config_manager.get_database_config()
        self.db_manager = DatabaseManager(db_config)

        # String 정보 캐시 (단순화)
        self.string_cache = {}
        
        self.setup_ui()
        self.setup_menu()
        self.setup_signals()
        
        # 로딩 오버레이 생성
        self.loading_overlay = LoadingOverlay(self)
        
        if LOGGING_AVAILABLE:
            self.log_manager = LogManager(self.config_manager)
            self.log_manager.operation_log("시스템", "RSD 모니터링 시스템 시작")
            self.log_manager.operation_log("설정", 
                f"설정: 통신 {self.config_manager.monitoring_communication_interval}초, "
                f"표시 {self.config_manager.monitoring_display_interval}초, "
                f"저장 {self.config_manager.monitoring_save_interval}초")


    def get_or_create_string_info(self, string_id: int) -> StringInfo:
        """String 정보를 가져오거나 생성 - 캐시 활용"""
        if string_id in self.string_cache:
            return self.string_cache[string_id]
        
        # 정보가 없으면 기본값으로 생성
        default_string_info = StringInfo(
            string_id=string_id,
            static_ip=f"192.168.1.{string_id}",
            rsd_count=0,
            description=f"String {string_id}",
            use_yn="Y"
        )
        
        self.string_cache[string_id] = default_string_info
        return default_string_info
    
    def setup_ui(self):
        """UI 구성"""
        self.setWindowTitle("RSD 실시간 모니터링 시스템")
        self.setGeometry(
            AppSettings.DEFAULT_WINDOW_X, 
            AppSettings.DEFAULT_WINDOW_Y, 
            AppSettings.DEFAULT_WINDOW_WIDTH, 
            AppSettings.DEFAULT_WINDOW_HEIGHT
        )
        
        # 중앙 위젯
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        
        # 메인 레이아웃
        main_layout = QVBoxLayout(central_widget)
        main_layout.setSpacing(8)
        main_layout.setContentsMargins(15, 15, 15, 15)
        
        # 제목 및 통계 정보
        header_layout = QVBoxLayout()
        
        title_label = QLabel("RSD 실시간 센싱 데이터 모니터링")
        title_label.setFont(QFont("Arial", 18, QFont.Bold))
        title_label.setAlignment(Qt.AlignCenter)
        title_label.setStyleSheet("color: #343a40; margin-bottom: 5px;")
        header_layout.addWidget(title_label)
        
        # 통계 정보 표시
        self.stats_label = QLabel(self.get_stats_text())
        self.stats_label.setFont(QFont("Arial", 11))
        self.stats_label.setAlignment(Qt.AlignCenter)
        self.stats_label.setStyleSheet("""
            color: #6c757d; 
            background-color: #e9ecef; 
            padding: 8px; 
            border-radius: 5px;
            margin-bottom: 10px;
        """)
        header_layout.addWidget(self.stats_label)
        
        main_layout.addLayout(header_layout)
        
        # 제어 버튼들
        button_layout = QHBoxLayout()
        
        self.start_button = QPushButton("모니터링 시작")
        self.start_button.setFont(QFont("Arial", 11, QFont.Bold))
        self.start_button.setStyleSheet("""
            QPushButton {
                background-color: #007bff;
                color: white;
                border: none;
                padding: 12px 25px;
                border-radius: 6px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #0056b3;
            }
            QPushButton:disabled {
                background-color: #6c757d;
            }
        """)
        
        self.stop_button = QPushButton("모니터링 중단")
        self.stop_button.setFont(QFont("Arial", 11, QFont.Bold))
        self.stop_button.setEnabled(False)
        self.stop_button.setStyleSheet("""
            QPushButton {
                background-color: #dc3545;
                color: white;
                border: none;
                padding: 12px 25px;
                border-radius: 6px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #c82333;
            }
            QPushButton:disabled {
                background-color: #6c757d;
            }
        """)
        
        button_layout.addWidget(self.start_button)
        button_layout.addWidget(self.stop_button)
        button_layout.addStretch()
        
        main_layout.addLayout(button_layout)
        
        # 스크롤 영역
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setStyleSheet("""
            QScrollArea {
                border: 1px solid #dee2e6;
                background-color: #f8f9fa;
                border-radius: 8px;
            }
        """)
        
        # String 데이터 표시 컨테이너
        self.string_container = QWidget()
        self.string_layout = QVBoxLayout(self.string_container)
        self.string_layout.setSpacing(8)
        self.string_layout.setContentsMargins(12, 12, 12, 12)
        
        # 초기 메시지
        self.show_initial_message()
        
        scroll_area.setWidget(self.string_container)
        main_layout.addWidget(scroll_area)
        
        # 상태바
        self.status_bar = QStatusBar()
        self.status_bar.showMessage("실시간 모니터링 준비됨")
        self.setStatusBar(self.status_bar)
        
    def setup_menu(self):
        """메뉴바 설정"""
        menubar = self.menuBar()
        
        # 설정 메뉴
        settings_menu = menubar.addMenu("설정")
        
        settings_action = QAction("모니터링 설정", self)
        settings_action.setShortcut("Ctrl+S")
        settings_action.triggered.connect(self.show_settings_dialog)
        settings_menu.addAction(settings_action)
        
        # 종료 메뉴
        exit_action = QAction("프로그램 종료", self)
        exit_action.setShortcut("Ctrl+Q")
        exit_action.triggered.connect(self.safe_exit)
        menubar.addAction(exit_action)
        
    def show_settings_dialog(self):
        """설정 다이얼로그 표시"""
        dialog = SettingsDialog(self.config_manager, self)
        if dialog.exec() == QDialog.Accepted:
            # 새 설정 적용 - ConfigManager 직접 사용
            communication_interval, display_interval, save_interval, rsd_communication_delay = dialog.get_updated_values()
            
            # ConfigManager의 설정 업데이트 (통신 간격 추가)
            self.config_manager.monitoring_communication_interval = communication_interval
            self.config_manager.monitoring_display_interval = display_interval
            self.config_manager.monitoring_save_interval = save_interval
            self.config_manager.monitoring_rsd_communication_delay = rsd_communication_delay
            self.config_manager.save_current_config()
            
            # 설정 변경 알림 (통신 주기 정보 추가)
            QMessageBox.information(
                self, "설정 저장", 
                f"설정이 저장되었습니다.\n\n"
                f"통신 주기: {communication_interval}초\n"
                f"표시 주기: {display_interval}초\n"
                f"저장 주기: {save_interval}초\n"
                f"RSD 개별 갱신: 각 RSD 통신시 즉시 갱신\n\n"
                f"변경사항은 다음 모니터링 시작시 적용됩니다."
            )
            
            if LOGGING_AVAILABLE and hasattr(self, 'log_manager'):
                self.log_manager.operation_log("설정", 
                    f"설정 변경: 통신 {communication_interval}초, "
                    f"표시 {display_interval}초, 저장 {save_interval}초")

    def safe_exit(self):
        """안전한 프로그램 종료를 요청합니다. (실제 로직은 closeEvent에 위임)"""
        self.close()

    def _final_cleanup_and_exit(self):
        """최종 리소스를 정리하고 애플리케이션을 종료합니다."""
        try:
            if self.log_manager:
                self.log_manager.operation_log("시스템", "최종 정리 및 종료 시작")

            if hasattr(self, 'loading_overlay'):
                self.loading_overlay.hide_loading()

            if hasattr(self, 'string_widgets'):
                self.string_widgets.clear()

            if hasattr(self, 'string_cache'):
                self.string_cache.clear()

            if self.log_manager:
                self.log_manager.operation_log("시스템", "프로그램 종료 완료")

        except Exception as e:
            if self.log_manager:
                self.log_manager.error_log("시스템", f"최종 정리 중 오류: {e}")
        finally:
            QApplication.quit()

    def setup_signals(self):
        """시그널 연결"""
        self.start_button.clicked.connect(self.start_monitoring)
        self.stop_button.clicked.connect(self.stop_monitoring)
    
    def get_stats_text(self):
        """통계 텍스트 반환"""
        return f"String: {self.total_string_count}개 | RSD: {self.total_rsd_count}개 | 상태: 대기 중"
    
    def show_initial_message(self):
        """초기 메시지 표시"""
        message_label = QLabel(
            "모니터링 시작 버튼을 눌러 실시간 RSD 통신을 시작하세요\n\n"
            "DB에서 활성 String/RSD 목록을 로드하여 실제 센싱 데이터를 수집합니다\n"
            "String별로 그룹화되어 표시되며, 각 RSD 통신 완료시 즉시 갱신됩니다\n\n"
            f"현재 설정: 통신 {self.config_manager.monitoring_communication_interval}초, "
            f"표시 {self.config_manager.monitoring_display_interval}초, "
            f"저장 {self.config_manager.monitoring_save_interval}초\n"
            "설정 변경은 메뉴의 '설정' → '모니터링 설정'에서 가능합니다"
        )
        message_label.setFont(QFont("Arial", 12))
        message_label.setAlignment(Qt.AlignCenter)
        message_label.setStyleSheet("""
            color: #495057; 
            padding: 50px; 
            background-color: #e9ecef; 
            border-radius: 8px; 
            margin: 20px;
            line-height: 1.8;
        """)
        self.string_layout.addWidget(message_label)

    def clear_string_widgets(self):
        """String 위젯들 초기화"""
        for widget in self.string_widgets.values():
            widget.setParent(None)
        self.string_widgets.clear()
        
        for i in reversed(range(self.string_layout.count())):
            self.string_layout.itemAt(i).widget().setParent(None)
    
    def _reset_ui_state(self):
        """UI 상태 완전 초기화"""
        # 버튼 상태 초기화
        self.start_button.setEnabled(True)
        self.stop_button.setEnabled(False)
        
        # 초기화 상태 플래그 리셋
        self.is_initializing = False
        
        # 로딩 오버레이 숨김
        if hasattr(self, 'loading_overlay'):
            self.loading_overlay.hide_loading()
        
        # 통계 카운트 초기화
        self.total_string_count = 0
        self.total_rsd_count = 0
        
        # 상태바 메시지 초기화
        self.status_bar.showMessage("모니터링 중지됨")
        
        # 통계 표시 초기화
        self.update_stats_display()
        
        if LOGGING_AVAILABLE and hasattr(self, 'log_manager'):
            self.log_manager.operation_log("UI", "UI 상태 완전 초기화 완료")
    
    def _initialize_ui_state(self):
        """UI 상태 초기화 시작"""
        # 버튼 상태 변경
        self.start_button.setEnabled(False)
        self.stop_button.setEnabled(True)
        
        # 기존 위젯 정리
        self.clear_string_widgets()
        
        # 통계 카운트 초기화
        self.total_string_count = 0
        self.total_rsd_count = 0
        
        # 초기화 상태 플래그 설정
        self.is_initializing = True
        
        # 로딩 오버레이 표시
        self.loading_overlay.show_loading(
            "모니터링 시작 중...",
            "시스템을 초기화하고 있습니다..."
        )
        
        if LOGGING_AVAILABLE and hasattr(self, 'log_manager'):
            self.log_manager.operation_log("UI", "UI 상태 초기화 시작")

    
    def start_monitoring(self):
        """모니터링 시작"""
        if self.monitoring_thread and self.monitoring_thread.isRunning():
            return
        
        self._initialize_ui_state()
        
        if LOGGING_AVAILABLE and hasattr(self, 'log_manager'):
            self.log_manager.operation_log("모니터링", "모니터링 시작 요청 - 시스템 초기화 시작")
        
        self.monitoring_thread = MonitoringThread(self.config_manager)
        self.monitoring_thread.data_updated.connect(self.update_rsd_data)
        self.monitoring_thread.single_rsd_updated.connect(self.update_single_rsd_data)
        self.monitoring_thread.status_updated.connect(self.update_status)
        self.monitoring_thread.error_occurred.connect(self.show_error)
        self.monitoring_thread.initialization_progress.connect(self.update_initialization_progress)
        self.monitoring_thread.backup_finished.connect(self._on_backup_finished)
        self.monitoring_thread.start()
        
        self.status_bar.showMessage("모니터링 시작됨")

    def _on_backup_finished(self, file_path: str):
        """
        데이터 백업 완료 시 사용자에게 알리는 슬롯
        """
        QMessageBox.warning(
            self,
            "데이터 백업 완료",
            f"데이터베이스 저장에 최종 실패하여 남은 데이터를 CSV 파일로 백업했습니다.\n\n"
            f"경로: {file_path}"
        )


    def stop_monitoring(self):
        """모니터링 중지 요청"""
        if not self.monitoring_thread or not self.monitoring_thread.isRunning():
            QMessageBox.information(self, "알림", "현재 모니터링이 실행 중이 아닙니다.")
            return

        # 새롭고 통합된 중지 요청 메서드를 호출합니다.
        self._request_monitoring_stop()

    def _request_monitoring_stop(self, is_exiting: bool = False):
        """
        모니터링 스레드의 안전한 중지를 요청하고 완료될 때까지 대기합니다.

        Args:
            is_exiting: 프로그램 종료의 일부로 호출되었는지 여부.
        """
        buffer_count = self.monitoring_thread.get_buffer_status().get('buffer_count', 0)
        
        if self.log_manager:
            log_message = "프로그램 종료를 위한 " if is_exiting else ""
            self.log_manager.operation_log("시스템", f"{log_message}모니터링 중지 요청 - 대기 데이터: {buffer_count}개")

        # 사용자에게 진행 상황 안내
        loading_title = "프로그램 종료 중..." if is_exiting else "모니터링 중지 중..."
        loading_detail = (
            f"남은 데이터 {buffer_count}개를 안전하게 저장하고 있습니다. 잠시만 기다려주세요..."
            if buffer_count > 0
            else "통신을 안전하게 종료하고 있습니다..."
        )
        self.loading_overlay.show_loading(loading_title, loading_detail)

        # UI 비활성화
        self.start_button.setEnabled(False)
        self.stop_button.setEnabled(False)

        # 스레드가 종료된 후 실행될 슬롯 연결
        # is_exiting 플래그를 전달하여, 스레드 종료 후 프로그램을 닫을지 결정
        self.monitoring_thread.finished.connect(
            lambda: self._on_monitoring_stopped(is_exiting)
        )

        # 스레드에 중지 요청
        self.monitoring_thread.stop()

    def _on_monitoring_stopped(self, is_exiting: bool):
        """
        모니터링 스레드가 완전히 종료된 후 UI를 정리하고, 필요시 프로그램을 종료합니다.
        
        Args:
            is_exiting: 프로그램 종료의 일부로 호출되었는지 여부.
        """
        self.loading_overlay.hide_loading()
        
        if self.log_manager:
            self.log_manager.operation_log("시스템", "모니터링 스레드 정상 종료 완료.")
            
        self._reset_ui_state()
        
        # is_exiting 플래그에 따라 프로그램 종료 여부 결정
        if is_exiting:
            self._final_cleanup_and_exit()
        else:
            QMessageBox.information(self, "완료", "모니터링이 안전하게 중지되었습니다.")



    def update_initialization_progress(self, message: str, detail: str):
        """초기화 진행상황 업데이트"""
        if self.is_initializing:
            self.loading_overlay.update_message(message, detail)
            
            if "완료" in message:
                self.is_initializing = False
                self.loading_overlay.hide_loading()
                
                if LOGGING_AVAILABLE and hasattr(self, 'log_manager'):
                    self.log_manager.operation_log("UI", "초기화 진행상황 업데이트 완료")
        else:
            # 초기화 중이 아닌데 메시지가 온 경우 로딩 오버레이 숨김
            if hasattr(self, 'loading_overlay'):
                self.loading_overlay.hide_loading()
            
            if LOGGING_AVAILABLE and hasattr(self, 'log_manager'):
                self.log_manager.operation_log("UI", "초기화 상태가 아닌 상태에서 진행상황 메시지 수신")
    
    def update_single_rsd_data(self, sensor_data: RSDSensorData):
        """단일 RSD 데이터 업데이트"""
        try:
            string_id = sensor_data.string_id
            
            if string_id not in self.string_widgets:
                # String 정보 생성 - 캐시 활용
                string_info = self.get_or_create_string_info(string_id)
                
                string_widget = StringGroupWidget(string_id, string_info)
                self.string_widgets[string_id] = string_widget
                self.string_layout.addWidget(string_widget)
                self.total_string_count += 1
        
            # 해당 RSD만 갱신
            self.string_widgets[string_id].update_rsd_data(sensor_data)
            
            # 통계 업데이트
            current_rsd_count = sum(widget.get_rsd_count() for widget in self.string_widgets.values())
            if current_rsd_count > self.total_rsd_count:
                self.total_rsd_count = current_rsd_count
                self.update_stats_display()
        
        except Exception as e:
            # logger.error() 제거하고 log_manager만 사용
            if LOGGING_AVAILABLE and hasattr(self, 'log_manager'):
                self.log_manager.error_log("UI", f"RSD 데이터 업데이트 오류: {e}")
            else:
                # log_manager가 없는 경우 기본 출력
                print(f"RSD 데이터 업데이트 오류: {e}")

    def update_rsd_data(self, sensor_data_list: List[RSDSensorData]):
        """기존 배치 갱신 메서드"""
        self.total_rsd_count = len(sensor_data_list)
        self.update_stats_display()
            
    def update_stats_display(self):
        """통계 정보 업데이트"""
        if self.monitoring_thread and self.monitoring_thread.isRunning():
            # 모니터링 중일 때
            status = "완전 클래스 기반 로깅" if LOGGING_AVAILABLE else "기본 로깅"
            status_text = (
                f"String: {self.total_string_count}개 | "
                f"RSD: {self.total_rsd_count}개 | "
                f"통신: {self.config_manager.monitoring_communication_interval}초 | "
                f"표시: {self.config_manager.monitoring_display_interval}초 | "
                f"저장: {self.config_manager.monitoring_save_interval}초 | "
                f"로깅: {status}"
            )
        else:
            # 대기 중일 때
            status_text = (
                f"대기 중... | "
                f"통신: {self.config_manager.monitoring_communication_interval}초 | "
                f"표시: {self.config_manager.monitoring_display_interval}초 | "
                f"저장: {self.config_manager.monitoring_save_interval}초"
            )
        
        self.status_bar.showMessage(status_text)

    def update_status(self, message: str):
        """상태 업데이트"""
        self.status_bar.showMessage(message)
        
    def show_error(self, error_message: str):
        """오류 메시지 표시"""
        # 모든 초기화 상태 리셋
        self._reset_ui_state()
        
        if LOGGING_AVAILABLE and hasattr(self, 'log_manager'):
            self.log_manager.error_log("시스템", f"시스템 오류: {error_message}")
        
        QMessageBox.critical(self, "오류", error_message)
        
        # 모니터링 중지
        if self.monitoring_thread and self.monitoring_thread.isRunning():
            self.monitoring_thread.stop()
            self.monitoring_thread.wait()
    
    def resizeEvent(self, event):
        """창 크기 변경시 로딩 오버레이 크기 조정"""
        super().resizeEvent(event)
        if hasattr(self, 'loading_overlay'):
            self.loading_overlay.resize(self.size())
    
    def closeEvent(self, event):
        """윈도우 종료 이벤트를 처리합니다."""
        # 1. 모니터링 스레드가 실행 중인 경우, 사용자에게 확인 후 안전하게 종료
        if self.monitoring_thread and self.monitoring_thread.isRunning():
            msg_box = QMessageBox(self)
            msg_box.setWindowTitle("종료 확인")
            msg_box.setText("모니터링이 진행중입니다.\n안전한 종료를 위해 모니터링 중단 후 프로그램 종료를 권장합니다.\n프로그램을 계속 종료하시겠습니까?")
            msg_box.setIcon(QMessageBox.Question)
            
            exit_button = msg_box.addButton("프로그램 종료", QMessageBox.DestructiveRole)
            confirm_button = msg_box.addButton("취소", QMessageBox.RejectRole)

            msg_box.exec()

            if msg_box.clickedButton() == exit_button:
                if self.log_manager:
                    self.log_manager.operation_log("시스템", "사용자가 프로그램 강제 종료를 선택했습니다.")
                # 기존 로직: 스레드를 안전하게 중지시키고, 스레드의 finally 블록에서 데이터 저장
                self._request_monitoring_stop(is_exiting=True)
                event.ignore() # 스레드가 종료될 때까지 대기
            else:
                event.ignore() # 종료 취소
            return

        # 2. 모니터링은 중지되었지만, 스레드 객체가 남아있고 버퍼에 데이터가 있을 수 있는 경우
        if self.monitoring_thread and hasattr(self.monitoring_thread, 'run_final_save_blocking'):
            buffer_count = self.monitoring_thread.get_buffer_status().get('buffer_count', 0)
            if buffer_count > 0:
                if self.log_manager:
                    self.log_manager.operation_log("시스템", f"종료 시 미저장 데이터 {buffer_count}개 발견.")
                
                self.loading_overlay.show_loading("데이터 저장 중...", f"남은 데이터 {buffer_count}개를 안전하게 저장합니다.")
                QApplication.processEvents()

                # 새로 추가한 블로킹 저장 메서드 호출
                self.monitoring_thread.run_final_save_blocking()
                
                self.loading_overlay.hide_loading()
        
        # 3. 모든 절차 후 실제 종료
        if self.is_exiting:
            event.accept()
            return

        self.is_exiting = True
        self._final_cleanup_and_exit()
        event.accept()

    def check_and_process_backups(self):
        """
        프로그램 시작 시, 저장되지 않은 백업 파일이 있는지 확인하고 처리를 묻습니다.
        (센서 데이터 및 로그 데이터 모두 처리)
        """
        try:
            # ===== 센서 데이터 백업 확인 =====
            backup_dir_data = "backup_data"
            has_data_backup = os.path.exists(backup_dir_data) and any(f.endswith('.csv') for f in os.listdir(backup_dir_data))

            # ===== 로그 데이터 백업 확인 =====
            backup_dir_logs = "backup_logs"
            has_log_backup = os.path.exists(backup_dir_logs) and any(f.endswith('.csv') for f in os.listdir(backup_dir_logs))

            if not has_data_backup and not has_log_backup:
                return # 백업 파일이 전혀 없으면 종료

            # 사용자에게 복구 여부 질문
            message = "데이터베이스에 저장되지 못한 백업 파일이 있습니다.\n"
            if has_data_backup:
                message += "- 센서 데이터\n"
            if has_log_backup:
                message += "- 로그 데이터\n"
            message += "\n지금 DB에 저장하시겠습니까?"

            reply = QMessageBox.question(self, '백업 데이터 복구', message,
                                         QMessageBox.Yes | QMessageBox.No, QMessageBox.No)

            if reply == QMessageBox.No:
                QMessageBox.information(self, '알림', '백업 데이터 복구를 취소했습니다.\n'
                                                    '파일은 다음 실행 시까지 유지됩니다.')
                return

            # 로딩 오버레이 표시
            self.loading_overlay.show_loading("백업 데이터 복구 중...",
                                              "백업된 CSV 파일을 DB에 저장하고 있습니다...")
            QApplication.processEvents()

            # 비동기 작업을 위한 이벤트 루프
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            
            # DB 매니저 초기화
            is_initialized = loop.run_until_complete(self.db_manager.initialize())
            
            summary_data = {'processed': 0, 'success': 0, 'failed': 0}
            summary_logs = {'processed': 0, 'success': 0, 'failed': 0}
            
            if is_initialized:
                # 센서 데이터 처리
                if has_data_backup:
                    summary_data = loop.run_until_complete(self.db_manager.process_pending_backups())
                # 로그 데이터 처리
                if has_log_backup:
                    summary_logs = loop.run_until_complete(self.db_manager.process_pending_log_backups())
                
                loop.run_until_complete(self.db_manager.close()) # 리소스 정리
            else:
                # 초기화 실패
                summary_data['failed'] = -1
                summary_logs['failed'] = -1

            loop.close()
            asyncio.set_event_loop(None)

            # 로딩 오버레이 숨김
            self.loading_overlay.hide_loading()
            
            # 결과 알림
            self._show_backup_result_message(summary_data, summary_logs)
        
        except Exception as e:
            self.loading_overlay.hide_loading()
            QMessageBox.critical(self, '오류', f'백업 데이터 처리 중 오류가 발생했습니다: {e}')

    def _show_backup_result_message(self, summary_data, summary_logs):
        """백업 처리 결과를 요약하여 메시지 박스로 표시합니다."""
        
        title = "복구 결과"
        final_message = ""
        is_critical = False
        is_warning = False

        # DB 연결 실패
        if summary_data.get('failed') == -1 or summary_logs.get('failed') == -1:
            final_message = "데이터베이스에 연결할 수 없어 복구를 진행하지 못했습니다."
            is_critical = True

        else:
            # 데이터 복구 결과
            if summary_data['processed'] > 0:
                if summary_data['failed'] > 0:
                    is_warning = True
                    final_message += (f"센서 데이터: 총 {summary_data['processed']}개 파일 중 "
                                      f"{summary_data['success']}개 성공, {summary_data['failed']}개 실패.\n")
                else:
                    final_message += f"센서 데이터: 총 {summary_data['processed']}개 파일을 모두 저장했습니다.\n"

            # 로그 복구 결과
            if summary_logs['processed'] > 0:
                if summary_logs['failed'] > 0:
                    is_warning = True
                    final_message += (f"로그 데이터: 총 {summary_logs['processed']}개 파일 중 "
                                      f"{summary_logs['success']}개 성공, {summary_logs['failed']}개 실패.\n")
                else:
                    final_message += f"로그 데이터: 총 {summary_logs['processed']}개 파일을 모두 저장했습니다.\n"

        final_message = final_message.strip()
        if not final_message:
            return # 보여줄 메시지가 없음

        if is_critical:
            QMessageBox.critical(self, title, final_message)
        elif is_warning:
            QMessageBox.warning(self, title, final_message)
        else:
            title = "복구 성공"
            QMessageBox.information(self, title, final_message)

# =============================================================================
# 메인 함수들
# =============================================================================

def setup_signal_handlers(app):
    """시그널 핸들러 설정"""
    def signal_handler(signum, frame):
        print("\n프로그램 종료 신호 수신 - 안전하게 종료합니다...")
        if hasattr(app, 'main_window') and app.main_window:
            app.main_window.safe_exit()
        else:
            app.quit()
    
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

def setup_logging():
    """기본 로깅 설정"""
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s'
    )

def get_application_style():
    """애플리케이션 스타일 반환"""
    return """
        QMainWindow {
            background-color: #ffffff;
        }
        QWidget {
            background-color: #ffffff;
            color: #212529;
        }
        QScrollBar:vertical {
            border: 1px solid #dee2e6;
            background: #f8f9fa;
            width: 12px;
            border-radius: 6px;
        }
        QScrollBar::handle:vertical {
            background: #ced4da;
            border-radius: 6px;
            min-height: 20px;
        }
        QScrollBar::handle:vertical:hover {
            background: #adb5bd;
        }
        QMenuBar {
            background-color: #f8f9fa;
            border-bottom: 1px solid #dee2e6;
        }
    """

def print_startup_info():
    """시작 정보 출력"""
    print("완전 클래스 기반 RSD 모니터링 시스템")
    print("LogManager 의존성 주입 패턴 적용")
    print("모니터링 중단 시 완전한 상태 초기화 개선")
    print("과한 모듈화 제거 - ConfigManager 직접 사용")
    if LOGGING_AVAILABLE:
        print("통합 로그 시스템 활성화")
    else:
        print("기본 로깅 모드")

def main():
    """메인 함수"""
    app = QApplication(sys.argv)
    
    # 시그널 핸들러 설정
    setup_signal_handlers(app)
    
    # 로깅 설정
    setup_logging()
    
    # 시작 정보 출력
    print_startup_info()
    
    # 애플리케이션 스타일 설정
    app.setStyleSheet(get_application_style())
    
    # 메인 윈도우 생성 및 표시
    window = RSDMonitoringMainWindow()
    app.main_window = window
    window.show()
    window.check_and_process_backups()
    
    print("RSD 모니터링 시스템이 시작되었습니다")
    print("완전 클래스 기반 구조로 효율적인 모니터링을 제공합니다")
    print("안전한 종료를 위해 Ctrl+C 또는 메뉴의 종료를 사용하세요")
    
    try:
        result = app.exec()
        
        if hasattr(app, 'main_window') and app.main_window:
            if hasattr(app.main_window, 'monitoring_thread') and app.main_window.monitoring_thread:
                if app.main_window.monitoring_thread.isRunning():
                    app.main_window.monitoring_thread.stop()
        
        print("프로그램이 정상적으로 종료되었습니다")
        return result
        
    except Exception as e:
        logging.error(f"애플리케이션 실행 오류: {e}")
        return 1
    finally:
        try:
            if hasattr(app, 'main_window'):
                del app.main_window
        except:
            pass


if __name__ == "__main__":
    sys.exit(main())