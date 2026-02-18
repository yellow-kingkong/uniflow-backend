from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import func
from typing import List, Optional
from datetime import datetime
import uuid

from app.database import get_db
from app.models import (
    User, SynergyService, SynergyApplication, HealthIndex, 
    Quest, AgentNote, ReferralReward, WithdrawalRequest, 
    Notification, UserNotification, Report
)
from pydantic import BaseModel
import uuid
import logging
from app.utils.mailer import send_vip_invite
from app.config import get_settings

logger = logging.getLogger(__name__)

router = APIRouter(tags=["agent"])

# --- Schemas ---

class MessageRequest(BaseModel):
    vip_id: str
    situation: str

class InviteRequest(BaseModel):
    vipName: str
    contactMethod: str  # email, phone
    email: Optional[str] = None
    phone: Optional[str] = None
    agentId: str

class VerifyAccountRequest(BaseModel):
    bank_name: str
    account_number: str
    account_holder: str

class WithdrawalRequestCreate(BaseModel):
    user_id: str
    amount: int
    bank_name: Optional[str] = None
    account_number: Optional[str] = None
    account_holder: Optional[str] = None

class WithdrawalHistoryItem(BaseModel):
    id: str
    amount: int
    status: str
    created_at: datetime

    class Config:
        from_attributes = True

# --- Helpers ---

def check_agent_subscription(agent: User):
    """에이전트 구독 상태 체크 및 접근 제어"""
    if agent.subscription_status == "blocked":
        raise HTTPException(status_code=403, detail="구독이 만료되어 계정이 차단되었습니다. 플랜을 갱신해 주세요.")
    
    if agent.subscription_status == "payment_failed":
        raise HTTPException(status_code=403, detail="결제 실패로 인해 기능이 제한되었습니다. 결제 수단을 확인해 주세요.")
    
    # expired 상태는 읽기 전용 (POST 요청에서 체크)
    return True

# --- Endpoints ---

@router.post("/verify-account")
def verify_account(req: VerifyAccountRequest):
    """실명 인증 Mock API"""
    # 실제로는 금융 API 연동 필요
    return {"message": "Success", "verified_name": req.account_holder}

@router.post("/invite-vip")
def invite_vip(req: InviteRequest, db: Session = Depends(get_db)):
    """VIP 초대 링크 발송 API (한도 및 구독 체크 포함)"""
    # 1. 에이전트 정보 및 구독 체크
    agent = db.query(User).filter(User.id == req.agentId).first()
    if not agent:
        raise HTTPException(status_code=404, detail="에이전트를 찾을 수 없습니다.")
    
    check_agent_subscription(agent)
    
    # 만료된 경우 (유예 기간 내) 초대 불가
    if agent.subscription_status == "expired":
        raise HTTPException(status_code=403, detail="구독이 만료되었습니다. 읽기 전용 모드에서는 초대하실 수 없습니다.")

    # 2. VIP 한도 체크
    if agent.vip_current_count >= agent.vip_limit:
        raise HTTPException(
            status_code=400, 
            detail=f"VIP 등록 한도({agent.vip_limit}명)를 초과했습니다. 플랜을 업그레이드 하세요."
        )

    settings = get_settings()
    invite_link = f"{settings.frontend_url}/invite/mock_token_{uuid.uuid4().hex[:8]}"
    target_email = req.email or req.phone # 실제로는 이메일 필수 권장
    
    if not target_email:
        raise HTTPException(status_code=400, detail="이메일 주소가 필요합니다.")
        
    # 실제 메일 발송
    success = send_vip_invite(target_email, req.vipName, invite_link)
    
    if success:
        return {
            "message": "이메일이 발송되었습니다.", 
            "invite_link": invite_link,
            "vip_name": req.vipName
        }
    else:
        logger.error(f"Failed to send invite to {target_email}")
        raise HTTPException(status_code=500, detail="이메일 발송에 실패했습니다. 다시 시도해주세요")

@router.get("/synergy")
def get_synergy_lineup(agent_id: str, db: Session = Depends(get_db)):
    """전체 시너지 서비스 및 신청 상태 조회"""
    services = db.query(SynergyService).all()
    # 해당 에이전트의 신청 내역 조회
    apps = db.query(SynergyApplication).filter(SynergyApplication.agent_id == agent_id).all()
    app_map = {a.service_id: a.status for a in apps}
    
    result = []
    for s in services:
        result.append({
            "id": s.id,
            "name": s.name,
            "description": s.description,
            "price": s.price,
            "status": app_map.get(s.id, "not_applied")
        })
    return result

@router.post("/onboarding/complete")
def complete_onboarding(agent_id: str, db: Session = Depends(get_db)):
    """온보딩 완료 처리"""
    agent = db.query(User).filter(User.id == agent_id).first()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    
    check_agent_subscription(agent)
    if agent.subscription_status == "expired":
        raise HTTPException(status_code=403, detail="읽기 전용 모드에서는 설정을 변경할 수 없습니다.")

    agent.onboarding_completed = True
    db.commit()
    return {"message": "Onboarding completed"}

@router.get("/dashboard/synergy")
def get_dashboard_synergy(agent_id: str, db: Session = Depends(get_db)):
    """에이전트용 시너지 라인업 현황"""
    services = db.query(SynergyService).all()
    applied_service_ids = [a.service_id for a in db.query(SynergyApplication).filter(SynergyApplication.agent_id == agent_id).all()]
    
    result = []
    for s in services:
        result.append({
            "id": s.id,
            "name": s.name,
            "description": s.description,
            "price": s.price,
            "is_applied": s.id in applied_service_ids
        })
    return result

@router.post("/synergy/apply")
def apply_synergy(service_id: str, agent_id: str, db: Session = Depends(get_db)):
    """시너지 서비스 영업 권한 신청 (구독 상태 체크)"""
    agent = db.query(User).filter(User.id == agent_id).first()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    
    check_agent_subscription(agent)
    if agent.subscription_status == "expired":
        raise HTTPException(status_code=403, detail="읽기 전용 모드에서는 신규 권한 신청이 불가능합니다.")

    existing = db.query(SynergyApplication).filter(
        SynergyApplication.service_id == service_id,
        SynergyApplication.agent_id == agent_id
    ).first()
    
    if existing:
        return {"message": "Already applied"}
    
    new_app = SynergyApplication(
        id=str(uuid.uuid4()),
        service_id=service_id,
        agent_id=agent_id,
        status="approved" # 에이전트 신청 시 즉시 승인 가정
    )
    db.add(new_app)
    db.commit()
    return {"message": "Success"}

@router.get("/vips")
def list_managed_vips(agent_id: str, db: Session = Depends(get_db)):
    """에이전트가 관리하는 VIP 리스트"""
    vips = db.query(User).filter(User.role == "vip", User.created_by == agent_id).all()
    
    result = []
    for vip in vips:
        # 최신 건강 점수 가져오기 (단순화: order by created_at)
        latest_score = db.query(HealthIndex).filter(HealthIndex.vip_id == vip.id).order_by(HealthIndex.created_at.desc()).first()
        score = latest_score.overall_score if latest_score else 0
        
        result.append({
            "id": vip.id,
            "name": vip.name,
            "email": vip.email,
            "overall_score": score,
            "last_update": vip.updated_at
        })
    return result

@router.post("/ai/message")
def generate_ai_message(req: MessageRequest):
    """AI 소통 도우미: Claude 연동 메시지 생성 (Staging/Mock)"""
    # 실제 구현은 Claude API 호출 로직 포함
    situations = {
        "정기 안부 인사": "안녕하세요 대표님, 한 주간 비즈니스는 어떠셨나요?",
        "건강 지표 피드백": "최근 시간 독립성 지표가 조금 낮아지셨네요. 잠시 쉬어가는 건 어떠실까요?",
        "시너지 서비스 제안": "대표님의 현재 상황에 딱 맞는 AI 자동화 솔루션이 새로 출시되어 제안드립니다.",
        "축하 메시지": "이번 달 목표 조기 달성을 진심으로 축하드립니다!"
    }
    msg = situations.get(req.situation, "안녕하세요!")
    return {"message": msg}

@router.get("/rewards")
def get_rewards_summary(agent_id: str, db: Session = Depends(get_db)):
    """에이전트 리워드 및 포인트 요약"""
    agent = db.query(User).filter(User.id == agent_id).first()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    
    rewards = db.query(ReferralReward).filter(ReferralReward.user_id == agent_id).all()
    withdrawals = db.query(WithdrawalRequest).filter(WithdrawalRequest.user_id == agent_id).all()
    
    return {
        "total_points": agent.points,
        "withdrawable_amount": agent.points,
        "monthly_referrals": 2, # Mock
        "total_referrals": len(rewards),
        "withdrawal_history": [
            {
                "id": w.id,
                "amount": w.amount,
                "status": w.status,
                "created_at": w.created_at
            } for w in withdrawals
        ]
    }

@router.post("/withdraw")
def request_withdrawal(req: WithdrawalRequestCreate, db: Session = Depends(get_db)):
    """출금 신청"""
    agent = db.query(User).filter(User.id == req.user_id).first()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
        
    check_agent_subscription(agent)
    if agent.subscription_status == "expired":
        raise HTTPException(status_code=403, detail="읽기 전용 모드에서는 출금 신청이 불가능합니다.")

    # 실제로는 agent.points 차감 및 로직 필요
    new_req = WithdrawalRequest(
        id=str(uuid.uuid4()),
        user_id=req.user_id,
        amount=req.amount,
        bank_name=req.bank_name,
        account_number=req.account_number,
        account_holder=req.account_holder,
        status="pending"
    )
    db.add(new_req)
    db.commit()
    return {"message": "Success"}
