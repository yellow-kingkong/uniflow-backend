"""
카카오톡 알림톡 발송 서비스
"""
import requests
from typing import Dict, Any
from app.config import get_settings

settings = get_settings()


class KakaoSender:
    """카카오톡 알림톡 발송"""
    
    def __init__(self):
        self.api_key = settings.kakao_api_key
        self.sender_key = settings.kakao_sender_key
        self.api_url = "https://api.kakao.com/v2/api/talk/send"
    
    def send_report(
        self,
        phone_number: str,
        report_url: str,
        user_data: Dict[str, Any]
    ) -> bool:
        """
        리포트 완성 알림톡 발송
        
        Args:
            phone_number: 수신자 전화번호
            report_url: 리포트 URL
            user_data: 사용자 정보 (name 등)
        
        Returns:
            발송 성공 여부
        """
        
        # 알림톡 템플릿
        template = {
            "template_code": "UNIFLOW_REPORT_001",
            "phone_number": phone_number,
            "variables": {
                "name": user_data.get("name", "대표님"),
                "report_url": report_url,
                "deadline": "48시간"
            }
        }
        
        try:
            response = requests.post(
                self.api_url,
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json"
                },
                json=template,
                timeout=10
            )
            
            return response.status_code == 200
        
        except Exception as e:
            print(f"카카오톡 발송 실패: {e}")
            return False
    
    def send_custom_message(
        self,
        phone_number: str,
        message: str
    ) -> bool:
        """커스텀 메시지 발송"""
        
        try:
            response = requests.post(
                self.api_url,
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json"
                },
                json={
                    "phone_number": phone_number,
                    "message": message
                },
                timeout=10
            )
            
            return response.status_code == 200
        
        except Exception as e:
            print(f"카카오톡 발송 실패: {e}")
            return False
