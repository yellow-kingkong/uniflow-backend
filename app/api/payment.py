from fastapi import APIRouter, Depends, HTTPException, Request, Header
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional
from datetime import datetime, timedelta
import uuid
import logging
import hmac
import hashlib
import base64
import os
import httpx

from app.database import get_db
from app.config import get_settings

router = APIRouter(tags=["payment"])
logger = logging.getLogger(__name__)

# ── 설정 ──────────────────────────────────────────────────────
settings = get_settings()

# 토스페이먼츠 API 기본 URL
TOSS_API_BASE = "https://api.tosspayments.com/v1"

def _get_toss_auth_header() -> str:
    """토스페이먼츠 Basic Auth 헤더값 생성"""
    secret_key = os.environ.get("TOSS_SECRET_KEY", "")
    if not secret_key:
        raise HTTPException(status_code=503, detail="Toss secret key not configured")
    # 시크릿 키 + ':' → Base64 인코딩
    token = base64.b64encode(f"{secret_key}:".encode()).decode()
    return f"Basic {token}"


# ── 요청 모델 ─────────────────────────────────────────────────
class UpgradeRequest(BaseModel):
    agent_id: str
    tier: str          # flow_one / flow_pro / flow_max / core_member
    billing_cycle: str = "monthly"   # monthly / yearly

class ConfirmRequest(BaseModel):
    paymentKey: str
    orderId: str
    amount: int


# ── 요금제 가격표 (백엔드 단일 진실 공급원) ────────────────────
TIER_PRICES: dict[str, dict[str, int]] = {
    "flow_one": {"monthly": 33000,  "yearly": 330000},
    "flow_pro": {"monthly": 55000,  "yearly": 550000},
    "flow_max": {"monthly": 99000,  "yearly": 950000},
}


# ── 토스 웹훅 서명 검증 ────────────────────────────────────────
def _verify_toss_signature(raw_body: bytes, toss_signature: str) -> bool:
    """
    토스페이먼츠 웹훅 서명 검증
    - 토스는 X-Toss-Signature 헤더에 HMAC-SHA256(시크릿키, rawBody) 값을 Base64로 전달
    - 공식 문서: https://docs.tosspayments.com/reference/webhook
    """
    secret_key = os.environ.get("TOSS_SECRET_KEY", "")
    if not secret_key:
        logger.warning("[Toss Webhook] TOSS_SECRET_KEY 미설정 — 서명 검증 생략")
        return False  # 키 없으면 실패 처리

    expected = hmac.new(
        secret_key.encode("utf-8"),
        raw_body,
        hashlib.sha256,
    ).digest()
    expected_b64 = base64.b64encode(expected).decode()

    return hmac.compare_digest(expected_b64, toss_signature)


# ── API 엔드포인트 ─────────────────────────────────────────────

@router.get("/subscription-status/{agent_id}")
def get_subscription_status(agent_id: str, db: Session = Depends(get_db)):
    """에이전트 구독 상태 조회"""
    from app.models import User
    agent = db.query(User).filter(User.id == agent_id).first()
    if not agent:
        raise HTTPException(status_code=404, detail="에이전트를 찾을 수 없습니다.")

    return {
        "tier": agent.tier,
        "status": agent.subscription_status,
        "trial_end_date": agent.trial_end_date,
        "subscription_end_date": agent.subscription_end_date,
        "special_discount": agent.special_discount,
        "grace_period_end_date": agent.grace_period_end_date,
    }


@router.post("/upgrade")
def upgrade_subscription(req: UpgradeRequest, db: Session = Depends(get_db)):
    """결제 전 단계: orderId / amount / clientKey 발급"""
    from app.models import User

    if req.tier not in TIER_PRICES:
        raise HTTPException(status_code=400, detail="유효하지 않은 요금제입니다.")
    if req.billing_cycle not in ("monthly", "yearly"):
        raise HTTPException(status_code=400, detail="billing_cycle은 monthly 또는 yearly여야 합니다.")

    agent = db.query(User).filter(User.id == req.agent_id).first()
    if not agent:
        raise HTTPException(status_code=404, detail="에이전트를 찾을 수 없습니다.")

    base_price = TIER_PRICES[req.tier][req.billing_cycle]

    # special_discount 적용
    discount = getattr(agent, "special_discount", 0) or 0
    final_price = int(base_price * (1 - discount / 100))

    client_key = os.environ.get("TOSS_CLIENT_KEY", "")
    if not client_key:
        raise HTTPException(status_code=503, detail="Toss client key not configured")

    return {
        "orderId":    str(uuid.uuid4()),
        "orderName":  f"UNIFLOW {req.tier} ({req.billing_cycle})",
        "amount":     final_price,
        "agentId":    req.agent_id,
        "tier":       req.tier,
        "billing_cycle": req.billing_cycle,
        "clientKey":  client_key,
    }


@router.post("/confirm")
async def confirm_payment(req: ConfirmRequest, db: Session = Depends(get_db)):
    """
    토스 결제 성공 redirect 후 최종 승인 요청
    프론트에서 paymentKey + orderId + amount를 받아 토스 서버에 재확인
    """
    from app.models import User

    # 1. 토스 서버에 최종 승인 요청
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{TOSS_API_BASE}/payments/confirm",
                headers={
                    "Authorization": _get_toss_auth_header(),
                    "Content-Type": "application/json",
                },
                json={
                    "paymentKey": req.paymentKey,
                    "orderId":    req.orderId,
                    "amount":     req.amount,
                },
                timeout=10.0,
            )
    except Exception as e:
        logger.error(f"[Toss Confirm] API 호출 실패: {e}")
        raise HTTPException(status_code=502, detail="토스 서버 통신 오류")

    if resp.status_code != 200:
        err_body = resp.json()
        logger.error(f"[Toss Confirm] 실패: {err_body}")
        raise HTTPException(
            status_code=400,
            detail=err_body.get("message", "결제 승인 실패"),
        )

    data = resp.json()
    # metadata에서 agentId, tier, billing_cycle 추출
    metadata = data.get("metadata") or {}
    agent_id     = metadata.get("agentId")
    tier         = metadata.get("tier", "flow_one")
    billing_cycle = metadata.get("billing_cycle", "monthly")

    if not agent_id:
        raise HTTPException(status_code=400, detail="metadata.agentId 누락")

    agent = db.query(User).filter(User.id == agent_id).first()
    if not agent:
        raise HTTPException(status_code=404, detail="에이전트를 찾을 수 없습니다.")

    _activate_subscription(agent, tier, billing_cycle, data)
    db.commit()

    return {"status": "success", "message": "구독이 활성화되었습니다."}


@router.post("/webhook/toss")
async def toss_webhook(
    request: Request,
    x_toss_signature: Optional[str] = Header(None, alias="X-Toss-Signature"),
    db: Session = Depends(get_db),
):
    """
    토스페이먼츠 웹훅 수신 및 처리
    - 서명 검증 후 결제 결과를 DB에 반영
    - 공식 문서: https://docs.tosspayments.com/reference/webhook
    """
    from app.models import User

    raw_body = await request.body()

    # ── 1. 서명 검증 ──────────────────────────────────────────
    if x_toss_signature:
        if not _verify_toss_signature(raw_body, x_toss_signature):
            logger.warning("[Toss Webhook] 서명 불일치 — 요청 거부")
            raise HTTPException(status_code=401, detail="Invalid webhook signature")
    else:
        # 서명 헤더가 없으면 개발 환경이거나 토스 설정 전 — 경고만
        logger.warning("[Toss Webhook] X-Toss-Signature 헤더 없음 (검증 생략)")

    # ── 2. 페이로드 파싱 ──────────────────────────────────────
    try:
        import json
        data = json.loads(raw_body)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON body")

    logger.info(f"[Toss Webhook] 수신: {data}")

    event_type = data.get("eventType", "")

    # 결제 완료 이벤트
    if event_type == "PAYMENT_STATUS_CHANGED":
        payment = data.get("data", {})
        status  = payment.get("status")

        if status != "DONE":
            # 취소·실패 등은 별도 처리 없이 200 반환
            logger.info(f"[Toss Webhook] 무시된 상태: {status}")
            return {"status": "ok", "message": f"Ignored status: {status}"}

        metadata      = payment.get("metadata") or {}
        agent_id      = metadata.get("agentId")
        tier          = metadata.get("tier", "flow_one")
        billing_cycle = metadata.get("billing_cycle", "monthly")

        if not agent_id:
            logger.error("[Toss Webhook] metadata.agentId 누락")
            return {"status": "error", "message": "Missing agentId in metadata"}

        agent = db.query(User).filter(User.id == agent_id).first()
        if not agent:
            logger.error(f"[Toss Webhook] 에이전트 없음: {agent_id}")
            return {"status": "error", "message": "Agent not found"}

        _activate_subscription(agent, tier, billing_cycle, payment)
        db.commit()
        return {"status": "success", "message": "Subscription activated"}

    # 정기 결제(자동갱신) 이벤트
    if event_type == "BILLING_KEY_ISSUED":
        billing_key = data.get("data", {}).get("billingKey")
        agent_id    = (data.get("data", {}).get("metadata") or {}).get("agentId")
        if billing_key and agent_id:
            agent = db.query(User).filter(User.id == agent_id).first()
            if agent:
                agent.billing_key = billing_key
                db.commit()
                logger.info(f"[Toss Webhook] billing_key 저장 완료: {agent_id}")
        return {"status": "ok"}

    return {"status": "ok", "message": f"Unhandled eventType: {event_type}"}


# ── 공통 헬퍼 ────────────────────────────────────────────────
def _activate_subscription(agent, tier: str, billing_cycle: str, payment_data: dict):
    """결제 완료 후 DB 상태 업데이트 (confirm / webhook 공용)"""
    now = datetime.now()
    days = 30 if billing_cycle == "monthly" else 365

    agent.tier                  = tier
    agent.subscription_type     = tier          # 기존 컬럼 병행 유지
    agent.subscription_status   = "active"
    agent.subscription_start_date = now
    agent.subscription_end_date = now + timedelta(days=days)
    agent.subscription_expires_at = now + timedelta(days=days)  # Supabase 컬럼
    agent.last_payment_date     = now
    agent.payment_method        = "tosspayments"

    # 빌링키 저장 (있는 경우)
    billing_key = payment_data.get("billingKey") or payment_data.get("billing_key")
    if billing_key:
        agent.billing_key = billing_key

    logger.info(f"[Payment] 구독 활성화: {agent.email} / {tier} / {billing_cycle}")
