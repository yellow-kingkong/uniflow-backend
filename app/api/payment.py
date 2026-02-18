from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional
from datetime import datetime, timedelta
import uuid
import logging

from app.database import get_db
from app.models import User, PointTransaction
from app.config import get_settings

router = APIRouter(tags=["payment"])
logger = logging.getLogger(__name__)

class UpgradeRequest(BaseModel):
    agent_id: str
    tier: str  # monthly, yearly
    payment_method: str = "tosspayments"

@router.get("/subscription-status/{agent_id}")
def get_subscription_status(agent_id: str, db: Session = Depends(get_db)):
    """에이전트 구독 상태 및 만료일 조회"""
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
    """구독 업그레이드 요청 (결제 전 단계)"""
    agent = db.query(User).filter(User.id == req.agent_id).first()
    if not agent:
        raise HTTPException(status_code=404, detail="에이전트를 찾을 수 없습니다.")
    
    # 등급별 가격 정보 (백엔드 검증용)
    prices = {
        "monthly": 99000,
        "yearly": 950000
    }
    
    if req.tier not in prices:
        raise HTTPException(status_code=400, detail="유효하지 않은 등급입니다.")
        
    return {
        "orderId": str(uuid.uuid4()),
        "orderName": f"UNIFLOW {req.tier.capitalize()} Plan",
        "amount": prices[req.tier],
        "agentId": req.agent_id,
        "tier": req.tier
    }

@router.post("/webhook/toss")
async def toss_webhook(request: Request, db: Session = Depends(get_db)):
    """토스페이먼츠 결제 결과 수신 웹훅"""
    data = await request.json()
    logger.info(f"Toss Webhook Received: {data}")
    
    # 에러 체크
    if data.get("status") == "FAILED":
        return {"status": "ok", "message": "Failure handled"}

    # 실제 결제 성공 처리 (가상 구현 - 실제 토스 API 연동 시 시크릿 키로 확인 절차 필요)
    # data에 포함된 orderId나 metadata를 통해 agent_id를 찾는다고 가정
    agent_id = data.get("metadata", {}).get("agentId")
    tier = data.get("metadata", {}).get("tier")
    
    if not agent_id or not tier:
        return {"status": "error", "message": "Missing metadata"}
        
    agent = db.query(User).filter(User.id == agent_id).first()
    if not agent:
        return {"status": "error", "message": "Agent not found"}
        
    # 1. 등급 및 상태 업데이트
    agent.tier = tier
    agent.subscription_status = "active"
    agent.subscription_start_date = datetime.now()
    agent.last_payment_date = datetime.now()
    agent.payment_method = "tosspayments"
    agent.vip_limit = 50 # 유료 등급은 무조건 50명 (기획안 기준)
    
    if tier == "monthly":
        agent.subscription_end_date = datetime.now() + timedelta(days=30)
    elif tier == "yearly":
        agent.subscription_end_date = datetime.now() + timedelta(days=365)
        
    # 2. 빌링키 저장 (자동 갱신용)
    if data.get("billingKey"):
        agent.billing_key = data.get("billingKey")
        
    db.commit()
    return {"status": "success", "message": "Subscription upgraded"}
