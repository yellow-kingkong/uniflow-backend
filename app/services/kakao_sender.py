"""
카카오 알림톡 발송 서비스 (SOLAPI 경유)
- 카카오 알림톡은 직접 API 없음 → 공식 파트너 SOLAPI를 통해서만 발송 가능
- SOLAPI 가입: https://solapi.com
- SOLAPI 카카오 채널 연결 후 pfId(채널키) 발급 필요
"""
import hashlib
import hmac
import time
import uuid
import requests
from typing import Dict, Any
from app.config import get_settings

settings = get_settings()


class KakaoSender:
    """카카오톡 알림톡 발송 (SOLAPI 파트너 API 사용)"""

    SOLAPI_URL = "https://api.solapi.com/messages/v4/send"

    def __init__(self):
        self.api_key = settings.kakao_api_key
        self.api_secret = settings.kakao_api_secret
        self.pf_id = settings.kakao_sender_key
        self.from_number = settings.kakao_sender_number

    def _is_configured(self) -> bool:
        return bool(self.api_key and self.api_secret and self.pf_id)

    def _make_auth_header(self) -> Dict[str, str]:
        """SOLAPI HMAC-SHA256 인증 헤더 생성"""
        date = str(int(time.time() * 1000))
        salt = str(uuid.uuid4())
        msg = date + salt
        signature = hmac.new(
            self.api_secret.encode("utf-8"),
            msg.encode("utf-8"),
            hashlib.sha256
        ).hexdigest()
        return {
            "Authorization": f"HMAC-SHA256 apiKey={self.api_key}, date={date}, salt={salt}, signature={signature}",
            "Content-Type": "application/json"
        }

    def send_report(self, phone_number: str, report_url: str, user_data: Dict[str, Any]) -> bool:
        """리포트 완성 알림톡 발송"""
        if not self._is_configured():
            print("카카오 알림톡 미설정 (SOLAPI 키 필요). 발송 건너뜀.")
            return False

        payload = {
            "message": {
                "to": phone_number.replace("-", ""),
                "from": self.from_number,
                "kakaoOptions": {
                    "pfId": self.pf_id,
                    "templateId": "UNIFLOW_REPORT_001",
                    "variables": {
                        "#{name}": user_data.get("name", "대표님"),
                        "#{report_url}": report_url,
                        "#{deadline}": "48시간"
                    }
                }
            }
        }

        try:
            response = requests.post(
                self.SOLAPI_URL,
                headers=self._make_auth_header(),
                json=payload,
                timeout=10
            )
            data = response.json()
            success = response.status_code == 200 and not data.get("errorCount", 0)
            if not success:
                print(f"알림톡 발송 실패: {data}")
            return success
        except Exception as e:
            print(f"카카오 알림톡 발송 오류: {e}")
            return False

    def send_invite(self, phone_number: str, invite_url: str, agent_name: str) -> bool:
        """VIP 초대 알림톡 발송"""
        if not self._is_configured():
            print("카카오 알림톡 미설정. 발송 건너뜀.")
            return False

        payload = {
            "message": {
                "to": phone_number.replace("-", ""),
                "from": self.from_number,
                "kakaoOptions": {
                    "pfId": self.pf_id,
                    "templateId": "UNIFLOW_INVITE_001",
                    "variables": {
                        "#{agent_name}": agent_name,
                        "#{invite_url}": invite_url
                    }
                }
            }
        }

        try:
            response = requests.post(
                self.SOLAPI_URL,
                headers=self._make_auth_header(),
                json=payload,
                timeout=10
            )
            return response.status_code == 200
        except Exception as e:
            print(f"초대 알림톡 발송 오류: {e}")
            return False
