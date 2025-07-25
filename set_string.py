"""
RSD String 관리 및 통신 테스트 모듈
TCP를 통한 RS485 통신으로 RSD 기기와 연결 테스트
기기 목록 구성과 테스트 통신만 담당
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
    """RSD 테스트 결과 클래스 (연결 테스트만)"""
    string_id: int
    rsd_id: int
    is_success: bool
    response_time: float
    error_message: str = ""


# =============================================================================
# RSD 프로토콜 처리 클래스 (테스트용)
# =============================================================================

class RSDProtocol:
    """RSD 통신 프로토콜 처리 클래스 (테스트 통신용)"""
    
    START_BYTE = 0x43
    FUNCTION_READ_DATA = 0x02
    CHANNEL_ALL = 0x00
    
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
    
    @classmethod
    def validate_response_header(cls, response_data: bytes) -> bool:
        """
        응답 패킷 헤더 검증 (테스트용 - 데이터 파싱하지 않음)
        
        Args:
            response_data: 응답 패킷 바이트
            
        Returns:
            헤더 유효성 여부
        """
        try:
            if len(response_data) < 5:
                return False
            
            # 헤더 파싱
            stx, addr, func, data_len = struct.unpack('BBBB', response_data[:4])
            
            if stx != cls.START_BYTE:
                return False
            
            if func != cls.FUNCTION_READ_DATA:
                return False
            
            # 데이터 길이 검증
            expected_length = 4 + data_len + 1
            if len(response_data) != expected_length:
                return False
            
            # 체크섬 검증
            received_checksum = response_data[-1]
            calculated_checksum = cls.calculate_checksum(response_data[:-1])
            
            return received_checksum == calculated_checksum
            
        except Exception as e:
            logger.debug(f"응답 헤더 검증 오류: {e}")
            return False


# =============================================================================
# String 관리 클래스
# =============================================================================

class StringManager:
    """String 관리 클래스 - String 정보 관리 전담"""
    
    def __init__(self):
        """String 관리자 초기화"""
        self.device_repository = None
        self.strings = {}
    
    def set_device_repository(self, device_repository):
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
            
        except Exception as e:
            logger.error(f"활성 String 목록 로드 실패: {e}")
            return []
    
    async def get_string_by_id(self, string_id: int) -> Optional[StringInfo]:
        """String ID로 String 정보 조회"""
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
        except Exception as e:
            logger.error(f"String {string_id} 조회 실패: {e}")
            return None
    
    def add_string(self, string_info: StringInfo):
        """String 정보 추가"""
        self.strings[string_info.string_id] = string_info


# =============================================================================
# RSD 관리 클래스
# =============================================================================

class RSDManager:
    """RSD 관리 클래스 - RSD 정보 관리 전담"""
    
    def __init__(self):
        """RSD 관리자 초기화"""
        self.device_repository = None
        self.devices = {}
    
    def set_device_repository(self, device_repository):
        self.device_repository = device_repository
    
    async def load_rsds_by_string(self, string_id: int) -> List[DeviceInfo]:
        """특정 String의 RSD 목록 로드"""
        if not self.device_repository:
            logger.error("Device repository가 설정되지 않았습니다")
            return []
            
        try:
            devices = await self.device_repository.get_active_devices_by_string(string_id)
            logger.info(f"String {string_id}의 RSD 목록 로드 완료: {len(devices)}개")
            return devices
            
        except Exception as e:
            logger.error(f"String {string_id}의 RSD 목록 로드 실패: {e}")
            return []
    
    async def get_rsd_by_id(self, string_id: int, rsd_id: int) -> Optional[DeviceInfo]:
        """RSD ID로 RSD 정보 조회"""
        try:
            devices = await self.device_repository.get_active_devices_by_string(string_id)
            for device in devices:
                if device.rsd_id == rsd_id:
                    return device
            return None
        except Exception as e:
            logger.error(f"RSD 조회 실패 - String {string_id}, RSD {rsd_id}: {e}")
            return None
    
    def add_device(self, device_info: DeviceInfo):
        """RSD 정보 추가"""
        key = f"{device_info.string_id}_{device_info.rsd_id}"
        self.devices[key] = device_info


# =============================================================================
# RSD 테스트 관리자 클래스
# =============================================================================

class RSDTestManager:
    """RSD 연결 테스트 전담 관리자"""
    
    def __init__(self, config: ConfigManager):
        """
        테스트 관리자 초기화
        
        Args:
            config: 설정 관리자
        """
        self.config = config
        self.protocol = RSDProtocol()
    
    async def test_rsd_connection(self, string_info: StringInfo, rsd_id: int, 
                                enable_retry: bool = False, retry_count: int = 1) -> RSDTestResult:
        """
        단일 RSD 연결 테스트 수행 (재시도 로직 추가)
        
        Args:
            string_info: String 정보
            rsd_id: RSD ID
            enable_retry: 재시도 활성화 여부 (기본값: False - 기존 동작 유지)
            retry_count: 재시도 횟수 (기본값: 1)
            
        Returns:
            테스트 결과
        """
        # 첫 번째 시도 (기존 코드 유지)
        first_result = await self._perform_single_test(string_info, rsd_id)
        
        # 재시도가 비활성화되어 있거나 첫 시도가 성공하면 기존 동작
        if not enable_retry or first_result.is_success:
            return first_result
        
        # 재시도 로직 (새로운 기능)
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
        특정 String의 모든 RSD 장치 테스트 (재시도 기능 추가)
        
        Args:
            string_info: String 정보
            device_list: 테스트할 RSD 장치 목록
            enable_retry: 재시도 활성화 여부 (기본값: False - 기존 동작 유지)
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
                
            except Exception as e:
                logger.error(f"String {string_info.string_id}, RSD {device.rsd_id} 테스트 중 예외: {e}")
                test_results.append(RSDTestResult(
                    string_id=string_info.string_id,
                    rsd_id=device.rsd_id,
                    is_success=False,
                    response_time=0.0,
                    error_message=f"테스트 예외: {str(e)}"
                ))
        
        success_count = sum(1 for r in test_results if r.is_success)
        failure_count = len(test_results) - success_count
        
        logger.info(f"String {string_info.string_id} 테스트 완료: 성공 {success_count}개, 실패 {failure_count}개")
        
        return test_results
    
    async def test_all_strings(self, string_manager: StringManager, rsd_manager: RSDManager,
                             enable_retry: bool = False, retry_count: int = 1) -> Dict[int, List[RSDTestResult]]:
        """
        모든 String에 대해 연결 테스트 수행 (재시도 기능 추가)
        
        Args:
            string_manager: String 관리자
            rsd_manager: RSD 관리자
            enable_retry: 재시도 활성화 여부 (기본값: False - 기존 동작 유지)
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
                
            except Exception as e:
                logger.error(f"String {string_info.string_id} 테스트 실패: {e}")
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
            'test_interval_used': self.config.monitoring_rsd_communication_delay  # 실제 사용된 간격 정보 추가
        }
    
    async def _perform_single_test(self, string_info: StringInfo, rsd_id: int) -> RSDTestResult:
        """
        단일 테스트 수행 (기존 test_rsd_connection의 핵심 로직)
        """
        start_time = datetime.now()
        
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
                
                # 응답 시간 계산
                response_time = (datetime.now() - start_time).total_seconds()
                
                if not response_data:
                    return RSDTestResult(
                        string_id=string_info.string_id,
                        rsd_id=rsd_id,
                        is_success=False,
                        response_time=response_time,
                        error_message="응답 없음"
                    )
                
                # 응답 헤더 검증
                is_valid = self.protocol.validate_response_header(response_data)
                
                return RSDTestResult(
                    string_id=string_info.string_id,
                    rsd_id=rsd_id,
                    is_success=is_valid,
                    response_time=response_time,
                    error_message="" if is_valid else "잘못된 응답 형식"
                )
                
            finally:
                writer.close()
                await writer.wait_closed()
                
        except asyncio.TimeoutError:
            response_time = (datetime.now() - start_time).total_seconds()
            return RSDTestResult(
                string_id=string_info.string_id,
                rsd_id=rsd_id,
                is_success=False,
                response_time=response_time,
                error_message="연결 타임아웃"
            )
            
        except Exception as e:
            response_time = (datetime.now() - start_time).total_seconds()
            return RSDTestResult(
                string_id=string_info.string_id,
                rsd_id=rsd_id,
                is_success=False,
                response_time=response_time,
                error_message=f"통신 오류: {str(e)}"
            )
        
    def get_test_summary(self, test_results: Dict[int, List[RSDTestResult]]) -> Dict[str, Any]:
        """
        테스트 결과 요약 정보 생성 (새 메서드)
        
        Args:
            test_results: String별 테스트 결과
            
        Returns:
            테스트 요약 정보
        """
        total_strings = len(test_results)
        active_strings = 0
        inactive_strings = 0
        total_rsds = 0
        active_rsds = 0
        
        string_details = {}
        
        for string_id, results in test_results.items():
            successful_rsds = [r for r in results if r.is_success]
            failed_rsds = [r for r in results if not r.is_success]
            
            total_rsds += len(results)
            active_rsds += len(successful_rsds)
            
            if successful_rsds:
                active_strings += 1
                string_status = "활성"
            else:
                inactive_strings += 1
                string_status = "비활성"
            
            string_details[string_id] = {
                'status': string_status,
                'total_rsds': len(results),
                'active_rsds': len(successful_rsds),
                'failed_rsds': len(failed_rsds),
                'success_rate': len(successful_rsds) / len(results) * 100 if results else 0
            }
        
        return {
            'total_strings': total_strings,
            'active_strings': active_strings,
            'inactive_strings': inactive_strings,
            'total_rsds': total_rsds,
            'active_rsds': active_rsds,
            'failed_rsds': total_rsds - active_rsds,
            'overall_success_rate': (active_rsds / total_rsds * 100) if total_rsds > 0 else 0,
            'string_details': string_details
        }