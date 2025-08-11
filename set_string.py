"""
RSD String 정보 관리 및 통신 연결 테스트
DB에서 String/RSD 장치 정보를 로드하고 관리
"""

import socket
import struct
import asyncio
import logging
from datetime import datetime
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass

from config_manager import ConfigManager
from db_manager import StringInfo, DeviceInfo

logger = logging.getLogger(__name__)


# =============================================================================
# 데이터 클래스 정의
# =============================================================================

@dataclass
class RSDTestResult:
    """"RSD 연결 테스트 결과를 저장"""
    string_id: int
    rsd_id: int
    is_success: bool
    response_time: float
    error_message: str = ""


# =============================================================================
# RSD 프로토콜 처리 클래스 (연결 테스트용)
# =============================================================================

class RSDProtocol:
    """RSD 통신 프로토콜 처리 클래스 (테스트 통신용)"""
    
    START_BYTE = 0x43
    FUNCTION_READ_DATA = 0x02
    CHANNEL_ALL = 0x00
    
    @staticmethod
    def calculate_checksum(data: bytes) -> int:
        """
        체크섬 계산 (하위 8비트)

        Args:
            data: 체크섬을 계산할 바이트 데이터
        """
        return sum(data) & 0xFF
    
    @classmethod
    def create_read_request(cls, slave_addr: int, channel_no: int = 0) -> bytes:
        """
        RSD 데이터 읽기 요청 패킷 생성
        
        Args:
            slave_addr: RSD ID
            channel_no: 채널 번호 (0=모든 채널)
            
        Returns:
            생성된 요청 패킷 (bytes)
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
    
    @classmethod
    def validate_response_header(cls, response_data: bytes) -> bool:
        """
        응답 패킷 헤더 검증 (테스트용)
        
        Args:
            response_data: 응답 패킷 (bytes)
            
        Returns:
            패킷이 유효하면 True, 그렇지 않으면 False
        """
        try:
            # 최소 패킷 길이(헤더 4 + 체크섬 1 = 5) 검증
            if len(response_data) < 5:
                logger.debug("응답 패킷 길이 부족")
                return False
            
            # 헤더 파싱
            try:
                stx, addr, func, data_len = struct.unpack('BBBB', response_data[:4])
            except struct.error as e:
                logger.debug(f"헤더 파싱 실패: {e}")
                return False
            
            # 시작 바이트 검증
            if stx != cls.START_BYTE:
                logger.debug(f"잘못된 시작 바이트: 0x{stx:02X} (기대값: 0x{cls.START_BYTE:02X})")
                return False
            
            # 기능 코드 검증
            if func != cls.FUNCTION_READ_DATA:
                logger.debug(f"잘못된 기능 코드: 0x{func:02X} (기대값: 0x{cls.FUNCTION_READ_DATA:02X})")
                return False
            
            # 전체 패킷 길이 검증
            expected_length = 4 + data_len + 1  # 헤더 + 데이터 + 체크섬
            if len(response_data) != expected_length:
                logger.debug(f"패킷 길이 불일치: {len(response_data)} (기대값: {expected_length})")
                return False
            
            # 체크섬 검증
            received_checksum = response_data[-1]
            calculated_checksum = cls.calculate_checksum(response_data[:-1])
            
            if received_checksum != calculated_checksum:
                logger.debug(f"체크섬 불일치: 0x{received_checksum:02X} (계산값: 0x{calculated_checksum:02X})")
                return False
            
            return True
            
        except (struct.error, IndexError) as e:
            logger.debug(f"패킷 구조 오류: {e}")
            return False
        except ValueError as e:
            logger.debug(f"패킷 값 오류: {e}")
            return False
        except Exception as e:
            logger.warning(f"패킷 검증 중 예상치 못한 오류: {e}")
            return False


# =============================================================================
# String 관리 클래스
# =============================================================================

class StringManager:
    """String 장치 정보 관리 클래스"""
    
    def __init__(self):
        self.device_repository = None
        self.strings = {}
    
    def set_device_repository(self, device_repository):
        """
        DB 조회를 위한 DeviceRepository를 설정(의존성 주입)

        Args:
            device_repository: DeviceRepository 객체
        """
        self.device_repository = device_repository
    
    async def load_active_strings(self) -> List[StringInfo]:
        """활성 String 목록 로드"""
        if not self.device_repository:
            logger.error("Device repository가 설정되지 않았습니다")
            return []
            
        try:
            strings = await self.device_repository.get_active_strings()
            
            # 내부 캐시 업데이트
            for string_info in strings:
                self.strings[string_info.string_id] = string_info
                
            logger.info(f"활성 String 목록 로드 완료: {len(strings)}개")
            return strings
            
        except asyncio.TimeoutError as e:
            logger.error(f"String 목록 로드 타임아웃: {e}")
            return []
        except ConnectionError as e:
            logger.error(f"DB 연결 오류로 String 목록 로드 실패: {e}")
            return []
        except ValueError as e:
            logger.error(f"String 데이터 형식 오류: {e}")
            return []
        except Exception as e:
            logger.error(f"활성 String 목록 로드 중 예상치 못한 오류: {e}")
            return []
    
    async def get_string_by_id(self, string_id: int) -> Optional[StringInfo]:
        """
        String ID로 String 정보 조회

        Args:
            string_id: 조회할 String ID
        """
        # 캐시에서 먼저 확인
        if string_id in self.strings:
            return self.strings[string_id]
            
        if not self.device_repository:
            logger.error("Device repository가 설정되지 않았습니다")
            return None
            
        try:
            string_info = await self.device_repository.get_string_info(string_id)
            if string_info:
                self.strings[string_id] = string_info
            return string_info
        except asyncio.TimeoutError as e:
            logger.error(f"String {string_id} 조회 타임아웃: {e}")
            return None
        except ConnectionError as e:
            logger.error(f"DB 연결 오류로 String {string_id} 조회 실패: {e}")
            return None
        except ValueError as e:
            logger.error(f"String {string_id} 데이터 형식 오류: {e}")
            return None
        except Exception as e:
            logger.error(f"String {string_id} 조회 중 예상치 못한 오류: {e}")
            return None
    
    def add_string(self, string_info: StringInfo):
        """
        String 정보 추가

        Args:
            string_info: 추가할 StringInfo 객체
        """
        self.strings[string_info.string_id] = string_info


# =============================================================================
# RSD 관리 클래스
# =============================================================================

class RSDManager:
    """RSD 장치 정보 관리 클래스"""
    
    def __init__(self):
        self.device_repository = None
        self.devices = {}
    
    def set_device_repository(self, device_repository):
        """
        DB 조회를 위한 DeviceRepository를 설정(의존성 주입)

        Args:
            device_repository: DeviceRepository 객체
        """
        self.device_repository = device_repository
    
    async def load_rsds_by_string(self, string_id: int) -> List[DeviceInfo]:
        """
        특정 String의 RSD 목록 로드

        Args:
            string_id: 조회할 String ID
        """
        if not self.device_repository:
            logger.error("Device repository가 설정되지 않았습니다")
            return []
            
        try:
            devices = await self.device_repository.get_active_devices_by_string(string_id)
            logger.info(f"String {string_id}의 RSD 목록 로드 완료: {len(devices)}개")
            return devices
            
        except asyncio.TimeoutError as e:
            logger.error(f"String {string_id}의 RSD 목록 로드 타임아웃: {e}")
            return []
        except ConnectionError as e:
            logger.error(f"DB 연결 오류로 String {string_id}의 RSD 목록 로드 실패: {e}")
            return []
        except ValueError as e:
            logger.error(f"String {string_id}의 RSD 데이터 형식 오류: {e}")
            return []
        except Exception as e:
            logger.error(f"String {string_id}의 RSD 목록 로드 중 예상치 못한 오류: {e}")
            return []
    
    async def get_rsd_by_id(self, string_id: int, rsd_id: int) -> Optional[DeviceInfo]:
        """
        RSD ID로 RSD 정보 조회

        Args:
            string_id: RSD가 속한 String ID
            rsd_id: 조회할 RSD ID
        """
        try:
            devices = await self.device_repository.get_active_devices_by_string(string_id)
            for device in devices:
                if device.rsd_id == rsd_id:
                    return device
            return None
        except asyncio.TimeoutError as e:
            logger.error(f"RSD 조회 타임아웃 - String {string_id}, RSD {rsd_id}: {e}")
            return None
        except ConnectionError as e:
            logger.error(f"DB 연결 오류로 RSD 조회 실패 - String {string_id}, RSD {rsd_id}: {e}")
            return None
        except ValueError as e:
            logger.error(f"RSD 데이터 형식 오류 - String {string_id}, RSD {rsd_id}: {e}")
            return None
        except Exception as e:
            logger.error(f"RSD 조회 중 예상치 못한 오류 - String {string_id}, RSD {rsd_id}: {e}")
            return None
    
    def add_device(self, device_info: DeviceInfo):
        """
        RSD ID로 RSD 정보 조회

        Args:
            string_id: RSD가 속한 String ID
            rsd_id: 조회할 RSD ID
        """
        key = f"{device_info.string_id}_{device_info.rsd_id}"
        self.devices[key] = device_info


# =============================================================================
# RSD 테스트 관리자 클래스
# =============================================================================

class RSDTestManager:
    """RSD 연결 테스트 전담 관리자"""
    
    def __init__(self, config: ConfigManager, alert_repository: Optional[Any] = None):
        """
        테스트 관리자 초기화
        
        Args:
            config: 설정 관리자
            alert_repository: 알림 저장소
        """
        self.config = config
        self.protocol = RSDProtocol()
        self.alert_repository = alert_repository

    async def test_rsd_connection(self, string_info: StringInfo, rsd_id: int, 
                                enable_retry: bool = False, retry_count: int = 1) -> RSDTestResult:
        """
        단일 RSD 연결 테스트 수행
        
        Args:
            string_info: String 정보
            rsd_id: RSD ID
            enable_retry: 재시도 활성화 여부
            retry_count: 재시도 횟수 (기본값: 1)
            
        Returns:
            테스트 결과
        """
        # 첫 번째 시도
        first_result = await self._perform_single_test(string_info, rsd_id)
        
        # 재시도가 비활성화되어 있거나 첫 시도가 성공하면 기존 동작
        if not enable_retry or first_result.is_success:
            return first_result
        
        # 재시도 로직
        logger.info(f"String {string_info.string_id}, RSD {rsd_id} 첫 시도 실패, {retry_count}회 재시도 수행")
        
        retry_results = [first_result]
        
        for attempt in range(retry_count):
            logger.debug(f"String {string_info.string_id}, RSD {rsd_id} 재시도 {attempt + 1}/{retry_count}")
            
            # 재시도 간격
            await asyncio.sleep(0.5)
            
            retry_result = await self._perform_single_test(string_info, rsd_id)
            retry_results.append(retry_result)
            
            if retry_result.is_success:
                logger.info(f"String {string_info.string_id}, RSD {rsd_id} 재시도 {attempt + 1}회 만에 성공")
                return retry_result
        
        # 모든 재시도 실패 시 종합 결과 반환
        last_result = retry_results[-1]
        total_attempts = len(retry_results)
        
        logger.warning(f"String {string_info.string_id}, RSD {rsd_id} 총 {total_attempts}회 시도 모두 실패")
        
        # 모든 오류 메시지 결합
        error_messages = [result.error_message for result in retry_results if result.error_message]
        combined_error = f"총 {total_attempts}회 시도 실패: {'; '.join(error_messages)}"
        
        return RSDTestResult(
            string_id=string_info.string_id,
            rsd_id=rsd_id,
            is_success=False,
            response_time=last_result.response_time,
            error_message=combined_error
        )

    async def test_string_devices(self, string_info: StringInfo, device_list: List[DeviceInfo],
                                enable_retry: bool = False, retry_count: int = 1) -> List[RSDTestResult]:
        """
        특정 String의 모든 RSD 장치 테스트
        
        Args:
            string_info: String 정보
            device_list: 테스트할 RSD 장치 목록
            enable_retry: 재시도 활성화 여부
            retry_count: 재시도 횟수 (기본값: 1)
            
        Returns:
            테스트 결과 리스트
        """
        test_results = []
        
        retry_suffix = f", 재시도 {retry_count}회" if enable_retry else ""
        logger.info(f"String {string_info.string_id} 테스트 시작: {len(device_list)}개 RSD{retry_suffix}")
        
        for i, device in enumerate(device_list):
            try:
                # 개별 RSD 테스트 (재시도 옵션 전달)
                result = await self.test_rsd_connection(
                    string_info, device.rsd_id, enable_retry, retry_count
                )
                test_results.append(result)
                
                # 테스트 결과 로깅
                status = "성공" if result.is_success else f"실패({result.error_message})"
                logger.debug(f"String {string_info.string_id}, RSD {device.rsd_id} 테스트: {status}")
                
                # 다음 기기까지 간격 유지
                if i < len(device_list) - 1:
                    delay = self.config.monitoring_rsd_communication_delay
                    await asyncio.sleep(delay)
                
            except asyncio.CancelledError:
                logger.warning(f"String {string_info.string_id}, RSD {device.rsd_id} 테스트 취소됨")
                test_results.append(RSDTestResult(
                    string_id=string_info.string_id,
                    rsd_id=device.rsd_id,
                    is_success=False,
                    response_time=0.0,
                    error_message="테스트 취소됨"
                ))
                raise  # 취소 신호는 상위로 전파
            except OSError as e:
                logger.error(f"String {string_info.string_id}, RSD {device.rsd_id} 네트워크 오류: {e}")
                test_results.append(RSDTestResult(
                    string_id=string_info.string_id,
                    rsd_id=device.rsd_id,
                    is_success=False,
                    response_time=0.0,
                    error_message=f"네트워크 오류: {str(e)}"
                ))
            except Exception as e:
                logger.error(f"String {string_info.string_id}, RSD {device.rsd_id} 테스트 중 예상치 못한 오류: {e}")
                test_results.append(RSDTestResult(
                    string_id=string_info.string_id,
                    rsd_id=device.rsd_id,
                    is_success=False,
                    response_time=0.0,
                    error_message=f"예상치 못한 오류: {str(e)}"
                ))
        
        success_count = sum(1 for r in test_results if r.is_success)
        failure_count = len(test_results) - success_count
        
        logger.info(f"String {string_info.string_id} 테스트 완료: 성공 {success_count}개, 실패 {failure_count}개")
        
        return test_results
    
    async def test_all_strings(self, string_manager: StringManager, rsd_manager: RSDManager,
                             enable_retry: bool = False, retry_count: int = 1) -> Dict[int, List[RSDTestResult]]:
        """
        시스템에 등록된 모든 활성 String 및 RSD에 대해 연결 테스트를 순차적으로 수행
        
        Args:
            string_manager: String 관리자
            rsd_manager: RSD 관리자
            enable_retry: 재시도 활성화 여부
            retry_count: 재시도 횟수 (기본값: 1)
            
        Returns:
            String ID별 테스트 결과 딕셔너리
        """
        # 활성 String 목록 로드
        strings = await string_manager.load_active_strings()
        
        if not strings:
            logger.warning("테스트할 String이 없습니다")
            return {}
        
        all_results = {}
        
        retry_suffix = f" (재시도 {retry_count}회)" if enable_retry else ""
        logger.info(f"전체 연결 테스트 시작: {len(strings)}개 String{retry_suffix}")
        
        for string_idx, string_info in enumerate(strings):
            try:
                logger.info(f"String {string_info.string_id} 테스트 시작 ({string_idx + 1}/{len(strings)})")
                
                # 해당 String의 RSD 목록 로드
                devices = await rsd_manager.load_rsds_by_string(string_info.string_id)
                
                if not devices:
                    logger.warning(f"String {string_info.string_id}에 테스트할 RSD가 없습니다")
                    all_results[string_info.string_id] = []
                    continue
                
                # String별 테스트 수행 (재시도 옵션 전달)
                string_results = await self.test_string_devices(
                    string_info, devices, enable_retry, retry_count
                )
                all_results[string_info.string_id] = string_results
                
                # 결과 로그 출력
                success_count = sum(1 for r in string_results if r.is_success)
                total_count = len(string_results)
                
                logger.info(f"String {string_info.string_id} 테스트 완료: {success_count}/{total_count} 성공")
                
                # String 간 간격
                if string_idx < len(strings) - 1:
                    await asyncio.sleep(0.1)
                
            except asyncio.CancelledError:
                logger.warning(f"String {string_info.string_id} 테스트 취소됨")
                all_results[string_info.string_id] = []
                raise  # 취소 신호는 상위로 전파
            except OSError as e:
                logger.error(f"String {string_info.string_id} 네트워크 오류로 테스트 실패: {e}")
                all_results[string_info.string_id] = []
            except Exception as e:
                logger.error(f"String {string_info.string_id} 테스트 중 예상치 못한 오류: {e}")
                all_results[string_info.string_id] = []
        
        # 전체 통계
        total_rsds = sum(len(results) for results in all_results.values())
        total_successes = sum(sum(1 for r in results if r.is_success) for results in all_results.values())
        
        logger.info(f"전체 테스트 완료: {total_successes}/{total_rsds} RSD 성공 ({total_successes/total_rsds*100:.1f}%)")
        
        return all_results

    
    def get_test_summary(self, all_results: Dict[int, List[RSDTestResult]]) -> Dict[str, Any]:
        """
        테스트 결과 요약 정보 생성
        
        Args:
            all_results: 모든 테스트 결과
            
        Returns:
            테스트 요약 정보
        """
        total_devices = 0
        successful_devices = 0
        failed_devices = 0
        total_response_time = 0.0
        
        string_summaries = []
        
        for string_id, results in all_results.items():
            if not results:
                continue
                
            string_success = sum(1 for r in results if r.is_success)
            string_total = len(results)
            string_failed = string_total - string_success
            
            string_avg_time = sum(r.response_time for r in results) / string_total if string_total > 0 else 0
            
            string_summaries.append({
                'string_id': string_id,
                'total_devices': string_total,
                'successful_devices': string_success,
                'failed_devices': string_failed,
                'success_rate': round((string_success / string_total * 100), 2) if string_total > 0 else 0,
                'avg_response_time': round(string_avg_time, 3)
            })
            
            total_devices += string_total
            successful_devices += string_success
            failed_devices += string_failed
            total_response_time += sum(r.response_time for r in results)
        
        return {
            'total_devices': total_devices,
            'successful_devices': successful_devices,
            'failed_devices': failed_devices,
            'overall_success_rate': round((successful_devices / total_devices * 100), 2) if total_devices > 0 else 0,
            'avg_response_time': round(total_response_time / total_devices, 3) if total_devices > 0 else 0,
            'string_summaries': string_summaries,
            'test_interval_used': self.config.monitoring_rsd_communication_delay
        }
    
    async def _perform_single_test(self, string_info: StringInfo, rsd_id: int) -> RSDTestResult:
        """
        단일 RSD에 대한 실제 통신 테스트를 수행하고 결과를 반환

        Args:
            string_info: 테스트할 RSD가 속한 String 정보
            rsd_id: 테스트할 RSD ID
        """
        start_time = datetime.now()
        error_message = ""
        is_success = False
        
        try:
            # TCP 연결 생성
            reader, writer = await asyncio.wait_for(
                asyncio.open_connection(
                    string_info.static_ip,
                    self.config.tcp_rsd_port
                ),
                timeout=self.config.tcp_connection_timeout
            )
            
            try:
                # 요청 패킷 생성 및 전송
                request_packet = self.protocol.create_read_request(rsd_id)
                writer.write(request_packet)
                await writer.drain()
                
                # 응답 수신
                response_data = await asyncio.wait_for(
                    reader.read(1024),
                    timeout=self.config.tcp_read_timeout
                )
                
                if not response_data:
                    error_message = "응답 없음"
                else:
                    # 응답 헤더 검증
                    is_success = self.protocol.validate_response_header(response_data)
                    if not is_success:
                        error_message = "잘못된 응답 형식"
                
            finally:
                writer.close()
                await writer.wait_closed()
                
        except asyncio.TimeoutError:
            error_message = "연결 타임아웃"
        except ConnectionRefusedError:
            error_message = "연결 거부됨"
        except OSError as e:
            error_message = f"네트워크 오류: {str(e)}"
        except Exception as e:
            error_message = f"예상치 못한 통신 오류: {str(e)}"

        response_time = (datetime.now() - start_time).total_seconds()

        # 테스트 실패 시 알림 저장
        if not is_success and self.alert_repository:
            try:
                await self.alert_repository.save_communication_error_alert(
                    string_id=string_info.string_id,
                    rsd_id=rsd_id,
                    error_message=f"연결 테스트 실패: {error_message}",
                    event_time=start_time
                )
            except Exception as e:
                logger.error(f"테스트 실패 알림 저장 중 오류 발생: {e}")

        return RSDTestResult(
            string_id=string_info.string_id,
            rsd_id=rsd_id,
            is_success=is_success,
            response_time=response_time,
            error_message=error_message
        )