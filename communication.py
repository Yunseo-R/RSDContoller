"""
RSD 통신 모듈
TCP/RS485 통신을 통한 실시간 센싱 데이터 수집
실제 모니터링 통신 전담
DatabaseManager Repository 패턴 호환
LogManager 의존성 주입 적용
save_sensor_data_batch 메서드 및 누락 기능 추가
"""

import socket
import struct
import asyncio
from typing import List, Dict, Optional, Any
from datetime import datetime

from config_manager import ConfigManager
from db_manager import (
    DatabaseManager,
    RSDSensorData, 
    StringInfo,
    DeviceInfo,
    ChannelData
)
from set_string import (
    StringManager,
    RSDManager
)


# =============================================================================
# RSD 프로토콜 처리 클래스
# =============================================================================

class RSDCommunicationProtocol:
    """RSD 실제 통신 프로토콜 처리 클래스 (센서 데이터 파싱 포함)"""
    
    START_BYTE = 0x43
    FUNCTION_READ_DATA = 0x02
    CHANNEL_ALL = 0x00
    
    def __init__(self, log_manager=None):
        """
        프로토콜 초기화
        
        Args:
            log_manager: LogManager 인스턴스 (선택사항)
        """
        self.log_manager = log_manager
    
    @staticmethod
    def calculate_checksum(data: bytes) -> int:
        """체크섬 계산 (하위 8비트)"""
        return sum(data) & 0xFF
    
    @classmethod
    def create_read_request(cls, slave_addr: int, channel_no: int = 0) -> bytes:
        """
        RSD 데이터 읽기 요청 패킷 생성
        
        Args:
            slave_addr: 슬레이브 주소 (RSD ID)
            channel_no: 채널 번호 (0=모든 채널)
            
        Returns:
            요청 패킷 바이트
        """
        data = struct.pack('B', channel_no)
        data_length = len(data)
        
        # 체크섬 계산
        checksum_data = struct.pack('BBBB', cls.START_BYTE, slave_addr, cls.FUNCTION_READ_DATA, data_length) + data
        checksum = cls.calculate_checksum(checksum_data)
        
        # 최종 패킷 조립
        packet = struct.pack('BBBB', cls.START_BYTE, slave_addr, cls.FUNCTION_READ_DATA, data_length)
        packet += data
        packet += struct.pack('B', checksum)
        
        return packet
    
    def parse_sensor_data(self, response_data: bytes, string_id: int) -> Optional[RSDSensorData]:
        """
        RSD 응답 패킷 파싱하여 센서 데이터 생성
        
        Args:
            response_data: 응답 패킷 바이트
            string_id: String ID
            
        Returns:
            파싱된 센서 데이터 또는 None
        """
        try:
            if len(response_data) < 5:
                if self.log_manager:
                    self.log_manager.error_log("프로토콜", f"응답 패킷이 너무 짧습니다: {len(response_data)} bytes")
                return None
            
            # 헤더 파싱
            stx, addr, func, data_len = struct.unpack('BBBB', response_data[:4])
            
            if stx != self.START_BYTE:
                if self.log_manager:
                    self.log_manager.error_log("프로토콜", f"잘못된 STX: 0x{stx:02X} (예상: 0x{self.START_BYTE:02X})")
                return None
            
            if func != self.FUNCTION_READ_DATA:
                if self.log_manager:
                    self.log_manager.error_log("프로토콜", f"잘못된 기능 코드: 0x{func:02X}")
                return None
            
            # 데이터 길이 검증
            expected_length = 4 + data_len + 1
            if len(response_data) != expected_length:
                if self.log_manager:
                    self.log_manager.error_log("프로토콜", f"패킷 길이 불일치: {len(response_data)} (예상: {expected_length})")
                return None
            
            # 체크섬 검증
            received_checksum = response_data[-1]
            calculated_checksum = self.calculate_checksum(response_data[:-1])
            
            if received_checksum != calculated_checksum:
                if self.log_manager:
                    self.log_manager.error_log("프로토콜", f"체크섬 오류: 수신={received_checksum:02X}, 계산={calculated_checksum:02X}")
                return None
            
            # 데이터 파싱
            data_bytes = response_data[4:4+data_len]
            
            # 채널 데이터 파싱 (각 채널당 9바이트)
            channel_data_size = 9
            if data_len % channel_data_size != 0:
                if self.log_manager:
                    self.log_manager.error_log("프로토콜", f"잘못된 데이터 길이: {data_len} (9의 배수가 아님)")
                return None
            
            channel_count = data_len // channel_data_size
            channels = []
            
            for i in range(channel_count):
                offset = i * channel_data_size
                channel_bytes = data_bytes[offset:offset+channel_data_size]
                
                if len(channel_bytes) != channel_data_size:
                    if self.log_manager:
                        self.log_manager.error_log("프로토콜", f"채널 {i+1} 데이터 크기 부족: {len(channel_bytes)}")
                    continue
                
                # 프로토콜 정의에 따른 채널 데이터 구조
                channel_no, current_h, current_l, temp_h, temp_l, arc_flag, arc_freq_h, arc_freq_l, arc_count = struct.unpack('BBBBBBBBB', channel_bytes)
                
                # 온도와 전류 값 계산
                temperature = (temp_h << 8) | temp_l
                current = (current_h << 8) | current_l
                arc_frequency = (arc_freq_h << 8) | arc_freq_l
                
                channel = ChannelData(
                    channel_no=channel_no,
                    temperature=float(temperature),
                    current=float(current),
                    is_arc=bool(arc_flag),
                    arc_frequency=arc_frequency,
                    arc_count=arc_count
                )
                channels.append(channel)
            
            return RSDSensorData(
                string_id=string_id,
                rsd_id=addr,
                rsd_status=0,
                channels=channels,
                timestamp=datetime.now()
            )
            
        except Exception as e:
            if self.log_manager:
                self.log_manager.error_log("프로토콜", f"응답 패킷 파싱 오류: {e}")
            return None


# =============================================================================
# 데이터 수집기 클래스
# =============================================================================

class RSDDataCollector:
    """RSD 데이터 수집기 - 실제 TCP 통신 담당"""
    
    def __init__(self, config: ConfigManager, log_manager=None, alert_repository=None):
        """
        데이터 수집기 초기화
        
        Args:
            config: 설정 관리자
            log_manager: LogManager 인스턴스
            alert_repository: AlertRepository 인스턴스
        """
        self.config = config
        self.log_manager = log_manager 
        self.protocol = RSDCommunicationProtocol(log_manager)
        self.alert_repository = alert_repository

    async def collect_string_data(self, string_info: StringInfo, 
                                 devices: List[DeviceInfo]) -> List[RSDSensorData]:
        """
        특정 String의 모든 RSD에서 센서 데이터 수집
        
        Args:
            string_info: String 정보
            devices: 해당 String의 RSD 목록
            
        Returns:
            수집된 센서 데이터 리스트
        """
        collected_data = []
        
        for i, device in enumerate(devices):
            data = await self._collect_single_rsd_data(string_info, device)
            if data:
                collected_data.append(data)
            
            # RSD 간 통신 간격
            if i < len(devices) - 1:
                await asyncio.sleep(self.config.monitoring_rsd_communication_delay)
        
        return collected_data
    
    async def _collect_single_rsd_data(self, string_info: StringInfo, 
                                     device: DeviceInfo) -> Optional[RSDSensorData]:
        """단일 RSD에서 센서 데이터 수집 (LogManager 로그 기록 추가)"""
        start_time = datetime.now()
        sock = None # 소켓 변수 초기화
        
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(self.config.tcp_connection_timeout)
            
            # TCP 연결
            sock.connect((string_info.static_ip, self.config.tcp_rsd_port))
            
            # 요청 패킷 생성 및 전송
            request_packet = self.protocol.create_read_request(device.rsd_id, 0)
            
            # 패킷 송신 로그 추가
            if self.log_manager and self.config.logging_packet_debug:
                self.log_manager.packet_log(string_info.string_id, device.rsd_id, 
                                          "send", request_packet.hex().upper())
            
            sock.send(request_packet)
            
            # 응답 수신
            sock.settimeout(self.config.tcp_read_timeout)
            response_data = sock.recv(self.config.tcp_buffer_size)
            
            # 패킷 수신 로그 추가
            if self.log_manager and self.config.logging_packet_debug:
                self.log_manager.packet_log(string_info.string_id, device.rsd_id, 
                                          "recv", response_data.hex().upper())
            
            duration = (datetime.now() - start_time).total_seconds()
            
            # 데이터 파싱
            sensor_data = self.protocol.parse_sensor_data(response_data, string_info.string_id)
            
            # 통신 결과 로그 추가
            if sensor_data and self.log_manager:
                self.log_manager.communication_log(
                    string_info.string_id, device.rsd_id, "sensor_poll", 
                    "success", duration, f"{len(sensor_data.channels)}개 채널"
                )
                
                # 아크 감지 로그 추가
                for channel in sensor_data.channels:
                    if channel.is_arc:
                        self.log_manager.arc_detection_log(
                            string_info.string_id, device.rsd_id, 
                            channel.channel_no, channel.arc_frequency, 
                            channel.arc_count
                        )
            elif self.log_manager:
                self.log_manager.communication_log(
                    string_info.string_id, device.rsd_id, "sensor_poll", 
                    "parse_error", duration, "데이터 파싱 실패"
                )
            
            return sensor_data
            
        except socket.timeout:
            duration = (datetime.now() - start_time).total_seconds()
            if self.log_manager:
                self.log_manager.communication_log(
                    string_info.string_id, device.rsd_id, "sensor_poll", "timeout", duration
                )
            if self.alert_repository:
                await self.alert_repository.save_communication_error_alert(
                    string_info.string_id, device.rsd_id, "Connection timeout",
                    event_time=start_time
                )
            return None
            
        except Exception as e:
            duration = (datetime.now() - start_time).total_seconds()
            if self.log_manager:
                self.log_manager.communication_log(
                    string_info.string_id, device.rsd_id, "sensor_poll", "error", duration, str(e)
                )
            if self.alert_repository:
                await self.alert_repository.save_communication_error_alert(
                    string_info.string_id, device.rsd_id, str(e),
                    event_time=start_time
                )
            return None
            
        finally:
            # ✅ 모든 경우에 소켓이 닫히도록 보장
            if sock:
                sock.close()


    async def close_all_connections(self):
        """
        데이터 수집기의 모든 연결을 종료합니다.
        (현재 구조에서는 요청마다 소켓을 생성/해제하므로 특별한 정리 로직이 필요하지 않으나,
         향후 소켓 풀링 등 확장성을 위해 메서드를 유지합니다.)
        """
        try:
            if self.log_manager:
                self.log_manager.operation_log("데이터수집", "데이터 수집기 연결 종료 시작")
            
            # 현재 활성 소켓이 있다면 종료 (향후 확장용)
            
            if self.log_manager:
                self.log_manager.operation_log("데이터수집", "데이터 수집기 연결 종료 완료")
                
        except Exception as e:
            if self.log_manager:
                self.log_manager.error_log("데이터수집", f"연결 종료 중 오류: {e}")


# =============================================================================
# 통신 관리자 클래스 (Repository 패턴 호환)
# =============================================================================

class CommunicationManager:
    """통신 관리자 - 데이터 수집 및 저장 통합 관리 (Repository 패턴 사용)"""
    
    def __init__(self, config: ConfigManager, db_manager: DatabaseManager, log_manager=None):
        """
        통신 관리자 초기화
        
        Args:
            config: 설정 관리자
            db_manager: 데이터베이스 관리자
            log_manager: LogManager 인스턴스 (선택사항)
        """
        self.config = config
        self.db_manager = db_manager
        self.log_manager = log_manager
        
        # Repository 접근
        self.sensor_repository = db_manager.get_sensor_repository()
        self.device_repository = db_manager.get_device_repository()
        self.alert_repository = db_manager.get_alert_repository()
        
        # RSDDataCollector 생성 시 alert_repository 전달
        self.data_collector = RSDDataCollector(config, log_manager, self.alert_repository)
        
        # 활성 기기 목록
        self.active_strings: List[StringInfo] = []
        self.active_devices: Dict[int, List[DeviceInfo]] = {}
        
        # 통계 초기화
        self._reset_statistics()

    def _reset_statistics(self) -> None:
        """통계 정보 초기화"""
        self.total_requests = 0
        self.successful_requests = 0
        self.failed_requests = 0
        self.last_collection_time = None
        self.response_times = []
    
    async def initialize(self) -> bool:
        """통신 관리자 초기화"""
        try:
            # 데이터베이스 초기화 확인
            if not self.db_manager.is_initialized():
                if self.log_manager:
                    self.log_manager.error_log("통신시스템", "데이터베이스가 초기화되지 않았습니다")
                return False
            
            # Repository 재할당 (초기화 후)
            self.sensor_repository = self.db_manager.get_sensor_repository()
            self.device_repository = self.db_manager.get_device_repository()
            self.alert_repository = self.db_manager.get_alert_repository()
            
            if not all([self.sensor_repository, self.device_repository, self.alert_repository]):
                if self.log_manager:
                    self.log_manager.error_log("통신시스템", "Repository 초기화 실패")
                return False
            
            if self.log_manager:
                self.log_manager.operation_log("통신시스템", "통신 관리자 초기화 완료")
            
            return True
            
        except Exception as e:
            if self.log_manager:
                self.log_manager.error_log("통신시스템", f"초기화 실패: {e}")
            return False
    
    def set_active_devices(self, strings: List[StringInfo], devices: List[DeviceInfo]) -> None:
        """활성 기기 목록 설정"""
        self.active_strings = strings
        self.active_devices = {}
        
        # String별로 디바이스 그룹화
        for device in devices:
            if device.string_id not in self.active_devices:
                self.active_devices[device.string_id] = []
            self.active_devices[device.string_id].append(device)
        
        if self.log_manager:
            total_devices = sum(len(devices) for devices in self.active_devices.values())
            self.log_manager.operation_log("통신시스템", 
                f"활성 기기 설정 완료: String {len(self.active_strings)}개, RSD {total_devices}개")
    

    async def collect_all_data(self) -> List[RSDSensorData]:
        """모든 활성 기기에서 데이터 수집 (원본 메서드명 유지)"""
        all_data = []
        start_time = datetime.now()
        
        try:
            for string_info in self.active_strings:
                if string_info.string_id in self.active_devices:
                    devices = self.active_devices[string_info.string_id]
                    string_data = await self.data_collector.collect_string_data(string_info, devices)
                    
                    # 아크 발생 즉시 알림 저장 로직 추가
                    if self.alert_repository:
                        for sensor_data in string_data:
                            for channel in sensor_data.channels:
                                if channel.is_arc:
                                    await self.alert_repository.save_arc_alert(
                                        sensor_data.string_id,
                                        sensor_data.rsd_id,
                                        channel.channel_no,
                                        channel.arc_frequency,
                                        channel.arc_count,
                                        event_time=sensor_data.timestamp
                                    )

                    all_data.extend(string_data)
                    
                    self.total_requests += len(devices)
                    self.successful_requests += len(string_data)
                    self.failed_requests += len(devices) - len(string_data)
            
            self.last_collection_time = datetime.now()
            
            if self.log_manager:
                duration = (self.last_collection_time - start_time).total_seconds()
                self.log_manager.operation_log("통신시스템", 
                    f"전체 데이터 수집 완료: {len(all_data)}개 RSD, {duration:.2f}초")
            
            return all_data
            
        except Exception as e:
            if self.log_manager:
                self.log_manager.error_log("통신시스템", f"데이터 수집 중 오류: {e}")
            return []


    async def save_collected_data(self, sensor_data_list: List[RSDSensorData]) -> int:
        """
        수집된 데이터를 데이터베이스에 저장합니다.

        Returns:
            저장된 레코드 개수
        """
        if not sensor_data_list:
            return 0

        try:
            # Repository를 통해 배치 저장
            result = await self.sensor_repository.save_sensor_data_batch(sensor_data_list)
            
            saved_count = result.get('success_count', 0)
            error_count = result.get('error_count', 0)
                        
            if self.log_manager:
                if error_count > 0:
                    self.log_manager.operation_log("데이터저장", 
                        f"데이터 저장 완료: 성공 {saved_count}개, 실패 {error_count}개")
                else:
                    self.log_manager.operation_log("데이터저장", 
                        f"데이터 저장 성공: {saved_count}개")
            
            return saved_count
            
        except Exception as e:
            if self.log_manager:
                self.log_manager.error_log("데이터저장", f"데이터 저장 실패: {e}")
            return 0

    async def save_sensor_data_batch(self, sensor_data_list: List[RSDSensorData]) -> Dict[str, int]:
        """
        센서 데이터 배치 저장 (호환성을 위한 메서드)
        
        Args:
            sensor_data_list: 저장할 센서 데이터 리스트
            
        Returns:
            저장 결과 딕셔너리 (success, error, total 개수)
        """
        if not sensor_data_list:
            return {
                'success': 0,
                'error': 0,
                'total': 0
            }
            
        try:
            # Repository를 통해 배치 저장
            result = await self.sensor_repository.save_sensor_data_batch(sensor_data_list)
            
            success_count = result.get('success_count', 0)
            error_count = result.get('error_count', 0)
            total_count = result.get('total_count', len(sensor_data_list))
            
            # 아크 발생 알림 처리
            await self._process_arc_alerts(sensor_data_list)
            
            # 통계 업데이트
            self._update_statistics(result, len(sensor_data_list))
            
            if self.log_manager:
                if error_count > 0:
                    self.log_manager.operation_log("데이터저장", 
                        f"배치 저장 완료: 성공 {success_count}개, 실패 {error_count}개")
                else:
                    self.log_manager.operation_log("데이터저장", 
                        f"배치 저장 성공: {success_count}개")
            
            return {
                'success': success_count,
                'error': error_count,
                'total': total_count
            }
            
        except Exception as e:
            if self.log_manager:
                self.log_manager.error_log("데이터저장", f"배치 저장 실패: {e}")
            self.failed_requests += len(sensor_data_list)
            return {
                'success': 0,
                'error': len(sensor_data_list),
                'total': len(sensor_data_list)
            }
    
    def _update_statistics(self, result: Dict[str, Any], total_count: int) -> None:
        """통계 정보 업데이트"""
        self.total_requests += total_count
        self.successful_requests += result.get('success_count', 0)
        self.failed_requests += result.get('error_count', 0)
    
    async def _process_arc_alerts(self, sensor_data_list: List[RSDSensorData]) -> None:
        """아크 발생 알림 처리"""
        for sensor_data in sensor_data_list:
            for channel in sensor_data.channels:
                if channel.is_arc:
                    try:
                        await self.alert_repository.save_arc_alert(
                            sensor_data.string_id,
                            sensor_data.rsd_id,
                            channel.channel_no,
                            channel.arc_frequency,
                            channel.arc_count,
                            event_time=sensor_data.timestamp
                        )
                        
                        # 아크 감지 로그
                        if self.log_manager:
                            self.log_manager.arc_detection_log(
                                sensor_data.string_id,
                                sensor_data.rsd_id,
                                channel.channel_no,
                                channel.arc_frequency,
                                channel.arc_count
                            )
                        
                    except Exception as e:
                        if self.log_manager:
                            self.log_manager.error_log("아크알림", 
                                f"아크 알림 저장 실패 - String {sensor_data.string_id}/RSD {sensor_data.rsd_id}/CH {channel.channel_no}: {e}")

    def get_statistics(self) -> Dict[str, Any]:
        """통신 통계 반환"""
        success_rate = (self.successful_requests / max(self.total_requests, 1)) * 100
        
        avg_response_time = 0.0
        if self.response_times:
            avg_response_time = sum(self.response_times) / len(self.response_times)
        
        return {
            'total_requests': self.total_requests,
            'successful_requests': self.successful_requests,
            'failed_requests': self.failed_requests,
            'success_rate': success_rate,
            'last_collection_time': self.last_collection_time,
            'active_strings': len(self.active_strings),
            'total_devices': sum(len(devices) for devices in self.active_devices.values()),
            'average_response_time': avg_response_time
        }
    
    async def close_all_connections(self):
        """모든 활성 연결 강제 종료"""
        try:
            if self.log_manager:
                self.log_manager.operation_log("통신시스템", "모든 연결 강제 종료 시작")
            
            # 데이터 수집기의 연결 종료
            if hasattr(self, 'data_collector') and self.data_collector:
                if hasattr(self.data_collector, 'close_all_connections'):
                    await self.data_collector.close_all_connections()
            
            # Repository 연결 종료
            if hasattr(self, 'sensor_repository') and self.sensor_repository:
                if hasattr(self.sensor_repository, 'close'):
                    await self.sensor_repository.close()
            
            if hasattr(self, 'device_repository') and self.device_repository:
                if hasattr(self.device_repository, 'close'):
                    await self.device_repository.close()
            
            if hasattr(self, 'alert_repository') and self.alert_repository:
                if hasattr(self.alert_repository, 'close'):
                    await self.alert_repository.close()
            
            # 활성 기기 정보 정리
            self.active_strings.clear()
            self.active_devices.clear()
            
            if self.log_manager:
                self.log_manager.operation_log("통신시스템", "모든 연결 강제 종료 완료")
                
        except Exception as e:
            if self.log_manager:
                self.log_manager.error_log("통신시스템", f"연결 종료 중 오류: {e}")
    
    def reset_statistics(self) -> None:
        """통신 통계 초기화 - 향상된 버전"""
        try:
            # 기존 통계 리셋
            self._reset_statistics()
            
            if self.log_manager:
                self.log_manager.operation_log("통신시스템", "통신 통계 초기화 완료")
                
        except Exception as e:
            if self.log_manager:
                self.log_manager.error_log("통신시스템", f"통계 리셋 중 오류: {e}")