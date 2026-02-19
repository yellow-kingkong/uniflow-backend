"""
토스페이먼츠 결제 처리 API
- POST /payment/upgrade: 결제 주문 정보 생성
- POST /payment/confirm: 결제 승인 (프론트 → 백엔드 → 토스 서버 검증)
- POST /payment/webhook/toss: 웹훅 수신
- GET  /payment/subscription-status/{agent_id}: 구독 상태 조회
"""
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional
from datetime import datetime, timedelta
import uuid
import logging
import httpx
import base64

from app.database import get_db
from app.models import User, PointTransaction
from app.config import get_settings

router = APIRouter(tags=["payment"])
logger = logging.getLogger(__name__)
settings = get_settings()

TOSS_API_URL = "https://api.tosspayments.com/v1"


class UpgradeRequest(BaseModel):
    agent_id: str
    tier: str  # monthly, yearly


class ConfirmRequest(BaseModel):
    paymentKey: str
    orderId: str
    amount: int


def _get_toss_auth_header() -> str:
    secret_key = settings.tosspayments_secret_key or ""
    encoded = base64.b64encode(f"{secret_key}:".encode()).decode()
    return f"Basic {encoded}"


@router.get("/subscription-status/{agent_id}")
def get_subscription_status(agent_id: str, db: Session = Depends(get_db)):
    """에이전트 구독 상태 조회"""
    agent = db.query(User).filter(User.id == agent_id).first()
    if not agent:
        raise HTTPException(status_code=404, detail="에이전트를 찾을 수 없습니다.")
    return {
        "tier": agent.tier,
        "status": agent.subscription_status,
        "trial_end_date": agent.trial_end_date,
        "subscription_end_date": agent.subscription_end_date,
        "vip_limit": agent.vip_limit,
        "vip_current_count": agent.vip_current_count,
        "grace_period_end_date": agent.grace_period_end_date
    }


@router.post("/upgrade")
def upgrade_subscription(req: UpgradeRequest, db: Session = Depends(get_db)):
    """결제 주문 정보 생성 (프론트엔드 위젯 초기화용)"""
    agent = db.query(User).filter(User.id == req.agent_id).first()
    if not agent:
        raise HTTPException(status_code=404, detail="에이전트를 찾을 수 없습니다.")

    if not settings.tosspayments_secret_key:
        raise HTTPException(
            status_code=503,
            detail="결제 시스템이 준비 중입니다. (TOSSPAYMENTS_SECRET_KEY 필요)"
        )

    prices = {"monthly": 99000, "yearly": 950000}
    if req.tier not in prices:
        raise HTTPException(status_code=400, detail="유효하지 않은 플랜입니다.")

    return {
        "orderId": str(uuid.uuid4()),
        "orderName": f"UNIFLOW {req.tier.capitalize()} Plan",
        "amount": prices[req.tier],
        "agentId": req.agent_id,
        "tier": req.tier,
        "clientKey": settings.tosspayments_client_key,
    }


@router.post("/confirm")
async def confirm_payment(req: ConfirmRequest, db: Session = Depends(get_db)):
    """토스페이먼츠 결제 최종 승인 및 구독 활성화"""
    if not settings.tosspayments_secret_key:
        raise HTTPException(status_code=503, detail="결제 시스템 미설정")

    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"{TOSS_API_URL}/payments/confirm",
            headers={
                "Authorization": _get_toss_auth_header(),
                "Content-Type": "application/json"
            },
            json={"paymentKey": req.paymentKey, "orderId": req.orderId, "amount": req.amount},
            timeout=30
        )

    toss_data = response.json()
    if response.status_code != 200:
        logger.error(f"토스 결제 승인 실패: {toss_data}")
        raise HTTPException(
            status_code=400,
            detail=f"결제 승인 실패: {toss_data.get('message', '알 수 없는 오류')}"
        )

    metadata = toss_data.get("metadata", {})
    agent_id = metadata.get("agentId")
    tier = metadata.get("tier")

    if not agent_id or not tier:
        raise HTTPException(status_code=400, detail="결제 메타데이터 누락")

    agent = db.query(User).filter(User.id == agent_id).first()
    if not agent:
        raise HTTPException(status_code=404, detail="에이전트를 찾을 수 없습니다.")

    agent.tier = tier
    agent.subscription_status = "active"
    agent.subscription_start_date = datetime.now()
    agent.last_payment_date = datetime.now()
    agent.payment_method = "tosspayments"
    agent.vip_limit = 50

    if tier == "monthly":
        agent.subscription_end_date = datetime.now() + timedelta(days=30)
    elif tier == "yearly":
        agent.subscription_end_date = datetime.now() + timedelta(days=365)

    if toss_data.get("billingKey"):
        agent.billing_key = toss_data.get("billingKey")

    db.commit()
    logger.info(f"결제 완료: agent={agent_id}, tier={tier}")
    return {"status": "success", "message": "구독이 활성화되었습니다.", "tier": tier}


@router.post("/webhook/toss")
async def toss_webhook(request: Request, db: Session = Depends(get_db)):
    """토스페이먼츠 웹훅 (자동 갱신)"""
    data = await request.json()
    logger.info(f"Toss Webhook: {data}")

    if data.get("status") == "FAILED":
        return {"status": "ok"}

    if data.get("type") == "BILLING":
        agent_id = data.get("metadata", {}).get("agentId")
        tier = data.get("metadata", {}).get("tier")
        if agent_id and tier:
            agent = db.query(User).filter(User.id == agent_id).first()
            if agent:
                agent.subscription_status = "active"
                agent.last_payment_date = datetime.now()
                if tier == "monthly":
                    agent.subscription_end_date = datetime.now() + timedelta(days=30)
                elif tier == "yearly":
                    agent.subscription_end_date = datetime.now() + timedelta(days=365)
                db.commit()

    return {"status": "ok"}
