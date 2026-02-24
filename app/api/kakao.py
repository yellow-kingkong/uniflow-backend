"""
카카오 알림톡 API 라우터 (Railway 서버 경유)
- Supabase Edge Function → 이 엔드포인트 → 알리고 API 순서로 호출
- Railway 서버의 고정 IP를 알리고에 등록하면 IP 인증 문제 해결
"""
from fastapi import APIRouter, HTTPException, Header
from pydantic import BaseModel
from typing import Optional, Dict
import requests
from app.config import get_settings

router = APIRouter()
settings = get_settings()

ALIGO_URL = "https://kakaoapi.aligo.in/akv10/alimtalk/send/"

# 6가지 알림톡 템플릿 정의 (send-kakao Edge Function과 동일)
KAKAO_TEMPLATES: Dict[str, Dict[str, str]] = {
    "expiry_d7": {
        "code": "EXP_D7",
        "content": "안녕하세요, #{이름}님.\n\nUNIFLOW 구독이 7일 후(#{만료일}) 만료될 예정입니다.\n만료 전 갱신 시 서비스를 중단 없이 이용하실 수 있습니다.\n\n[구독 갱신]\n#{갱신링크}",
    },
    "expiry_d1": {
        "code": "EXP_D1",
        "content": "안녕하세요, #{이름}님.\n\n구독이 내일(#{만료일}) 만료됩니다.\n계속 이용을 원하시면 아래 링크에서 갱신해 주세요.\n\n[구독 갱신]\n#{갱신링크}",
    },
    "expiry_d0": {
        "code": "EXP_D0",
        "content": "안녕하세요, #{이름}님.\n\nUNIFLOW 구독이 오늘(#{만료일}) 만료되었습니다.\n서비스 재이용을 원하시면 아래 링크에서 갱신해 주세요.\n\n[구독 갱신]\n#{갱신링크}",
    },
    "agent_invite": {
        "code": "AGT_INV",
        "content": "안녕하세요.\n\nUNIFLOW 서비스의 에이전트로 초대되셨습니다.\n아래 링크를 통해 회원가입 후 활동을 시작하실 수 있습니다.\n\n[초대 링크]\n#{초대링크}\n\n링크 유효기간: 7일",
    },
    "vip_invite": {
        "code": "VIP_INV",
        "content": "안녕하세요.\n\n#{에이전트이름} 에이전트님을 통해 UNIFLOW VIP 회원으로 초대되셨습니다.\n\n[초대 링크]\n#{초대링크}\n\n링크 유효기간: 7일",
    },
    "admin_notice": {
        "code": "ADN_NOT",
        "content": "[UNIFLOW 공지사항]\n\n#{공지제목}\n\n#{공지내용}\n\n자세한 내용은 UNIFLOW 앱에서 확인하세요.",
    },
}


class SendKakaoRequest(BaseModel):
    """알림톡 발송 요청 모델"""
    type: Optional[str] = None          # 템플릿 종류 (expiry_d7 등)
    phone: str                          # 수신자 번호 (01012345678)
    variables: Optional[Dict[str, str]] = None  # 템플릿 변수 치환값
    template_code: Optional[str] = None  # 직접 지정 시 템플릿 코드
    message: Optional[str] = None        # 직접 지정 시 메시지 내용
    fail_sms: bool = True               # 알림톡 실패 시 SMS 대체 여부


def _apply_variables(template: str, variables: Dict[str, str]) -> str:
    """템플릿 변수 치환 (#{변수명} → 실제값)"""
    result = template
    for key, value in variables.items():
        result = result.replace(key, value)
    return result


@router.post("/send")
async def send_kakao(
    request: SendKakaoRequest,
    x_internal_secret: Optional[str] = Header(None),
):
    """
    카카오 알림톡 발송 엔드포인트
    - Supabase Edge Function에서 내부 시크릿 헤더와 함께 호출
    - Railway 고정 IP → 알리고 API 호출 (IP 인증 문제 해결)
    """
    # 내부 호출 인증 (X-Internal-Secret 헤더 검증)
    if x_internal_secret != settings.internal_secret:
        raise HTTPException(status_code=403, detail="Unauthorized internal call")

    # 알리고 설정 확인
    if not settings.kakao_api_key or not settings.kakao_api_secret:
        raise HTTPException(status_code=500, detail="알리고 API 키가 설정되지 않았습니다")

    # 템플릿 코드 및 메시지 결정
    if request.type and request.type in KAKAO_TEMPLATES:
        tpl = KAKAO_TEMPLATES[request.type]
        template_code = tpl["code"]
        message = _apply_variables(tpl["content"], request.variables or {})
    elif request.template_code and request.message:
        template_code = request.template_code
        message = _apply_variables(request.message, request.variables or {})
    else:
        raise HTTPException(status_code=400, detail="type 또는 template_code+message 필요")

    # 전화번호 정규화 (010-1234-5678 → 01012345678)
    clean_phone = request.phone.replace("-", "")

    # 알리고 API 호출
    payload = {
        "apikey": settings.kakao_api_key,
        "userid": settings.kakao_api_secret,
        "senderkey": settings.kakao_sender_key,
        "tpl_code": template_code,
        "sender": settings.kakao_sender_number,
        "receiver_1": clean_phone,
        "subject_1": "UNIFLOW",
        "message_1": message,
        "failover": "Y" if request.fail_sms else "N",
        "fsubject_1": "UNIFLOW" if request.fail_sms else "",
        "fmessage_1": message if request.fail_sms else "",
    }

    try:
        resp = requests.post(ALIGO_URL, data=payload, timeout=10)
        data = resp.json()
        success = data.get("code") == 0
        if not success:
            print(f"[알림톡 실패] {clean_phone}: {data.get('message')}")
        return {
            "success": success,
            "code": data.get("code"),
            "message": data.get("message", ""),
        }
    except Exception as e:
        print(f"[알리고 API 오류]: {e}")
        raise HTTPException(status_code=502, detail=f"알리고 API 오류: {str(e)}")
