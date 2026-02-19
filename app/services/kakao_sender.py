"""
카카오 알림톡 발송 서비스 (알리고 경유)
- 알리고 가입: https://www.aligo.in
- 카카오 알림톡 신청 후 발신프로필키(senderkey) 발급 필요
"""
import requests
from typing import Dict, Any
from app.config import get_settings

settings = get_settings()

# 알리고 API 엔드포인트
ALIGO_URL = "https://kakaoapi.aligo.in/akv10/alimtalk/send/"


class KakaoSender:
    """카카오 알림톡 발송 (알리고 API 사용)"""

    def __init__(self):
        self.api_key = settings.kakao_api_key       # 알리고 API Key
        self.user_id = settings.kakao_api_secret    # 알리고 ID (userid)
        self.sender_key = settings.kakao_sender_key  # 발신프로필키
        self.sender = settings.kakao_sender_number   # 발신번호

    def _is_configured(self) -> bool:
        return bool(self.api_key and self.user_id and self.sender_key)

    def send_report(self, phone_number: str, report_url: str, user_data: Dict[str, Any]) -> bool:
        """리포트 완성 알림톡 발송"""
        if not self._is_configured():
            print("카카오 알림톡 미설정 (알리고 키 필요). 발송 건너뜀.")
            return False

        name = user_data.get("name", "대표님")
        message = (
            f"[UNIFLOW] {name}, 비즈니스 진단 리포트가 완성되었습니다.\n\n"
            f"리포트 확인: {report_url}\n\n"
            f"48시간 내 확인해주세요."
        )

        payload = {
            "apikey": self.api_key,
            "userid": self.user_id,
            "senderkey": self.sender_key,
            "tpl_code": "UNIFLOW_REPORT",   # 알리고에 등록한 템플릿 코드
            "sender": self.sender,
            "receiver_1": phone_number.replace("-", ""),
            "subject_1": "UNIFLOW 리포트 완성",
            "message_1": message,
            "failover": "Y",   # 알림톡 실패 시 SMS로 대체 발송
        }

        try:
            response = requests.post(ALIGO_URL, data=payload, timeout=10)
            data = response.json()
            success = data.get("code") == 0
            if not success:
                print(f"알림톡 발송 실패: {data.get('message')}")
            return success
        except Exception as e:
            print(f"카카오 알림톡 오류: {e}")
            return False

    def send_invite(self, phone_number: str, invite_url: str, agent_name: str) -> bool:
        """VIP 초대 알림톡 발송"""
        if not self._is_configured():
            print("카카오 알림톡 미설정. 발송 건너뜀.")
            return False

        message = (
            f"[UNIFLOW] {agent_name} 에이전트가 초대했습니다.\n\n"
            f"초대 수락: {invite_url}"
        )

        payload = {
            "apikey": self.api_key,
            "userid": self.user_id,
            "senderkey": self.sender_key,
            "tpl_code": "UNIFLOW_INVITE",   # 알리고에 등록한 템플릿 코드
            "sender": self.sender,
            "receiver_1": phone_number.replace("-", ""),
            "subject_1": "UNIFLOW VIP 초대",
            "message_1": message,
            "failover": "Y",
        }

        try:
            response = requests.post(ALIGO_URL, data=payload, timeout=10)
            data = response.json()
            return data.get("code") == 0
        except Exception as e:
            print(f"초대 알림톡 오류: {e}")
            return False
