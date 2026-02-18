from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import func
from typing import List, Optional
from datetime import datetime, timedelta

from app.database import get_db
from app.models import (
    User, AgentApplication, SolutionRequest, Notification, 
    UserNotification, SynergyService, Report, SolutionHistory,
    PointTransaction, WithdrawalRequest, SessionPayment, Quest, HealthIndex,
    InvitationToken
)
from pydantic import BaseModel
import uuid

router = APIRouter(tags=["admin"])

# --- Schemas ---

class KPISummary(BaseModel):
    total_agents: int
    total_vips: int
    expected_revenue: int
    pending_notifications: int
    agent_growth_rate: float
    vip_growth_rate: float

class RealtimeStats(BaseModel):
    today_new_agents: int
    today_new_vips: int
    weekly_completed_deals: int
    monthly_withdrawal_points: int

class SolutionStatusUpdateRequest(BaseModel):
    status: str
    memo: Optional[str] = None
    processing_type: Optional[str] = None # direct, expert
    admin_id: str

class InvitationCreateRequest(BaseModel):
    name: str
    email: str
    admin_id: str

class AgentUpdateRequest(BaseModel):
    name: Optional[str] = None
    email: Optional[str] = None
    vip_limit: Optional[int] = None
    memo: Optional[str] = None

class PointAdjustRequest(BaseModel):
    amount: int
    type: str # add, deduct
    reason: Optional[str] = None

class SettlementStatusUpdate(BaseModel):
    status: str # approved, rejected, paid
    memo: Optional[str] = None

class SessionPaymentUpdate(BaseModel):
    payment_status: str # pending, completed, cancelled
    session_date: Optional[datetime] = None

# 신규 어드민 관리 스키마
class TierUpdateRequest(BaseModel):
    tier: str
    admin_id: str

class StatusUpdateRequest(BaseModel):
    subscription_status: str
    admin_id: str

class ExtensionRequest(BaseModel):
    subscription_end_date: Optional[str] = None
    days: Optional[int] = None
    admin_id: str

class BulkExtensionRequest(BaseModel):
    agent_ids: List[str]
    days: int
    admin_id: str

class AgentPartialUpdateRequest(BaseModel):
    name: Optional[str] = None
    tier: Optional[str] = None
    subscription_status: Optional[str] = None
    vip_limit: Optional[int] = None
    subscription_end_date: Optional[str] = None
    admin_id: str

# --- Helpers ---

from app.models import AdminAction
import json

def log_admin_action(db: Session, admin_id: str, action_type: str, target_id: str, old_val: any, new_val: any):
    """관리자 활동 로그 기록"""
    action = AdminAction(
        admin_id=admin_id,
        action_type=action_type,
        target_agent_id=target_id,
        old_value=json.dumps(old_val, default=str) if old_val else None,
        new_value=json.dumps(new_val, default=str) if new_val else None
    )
    db.add(action)

def verify_admin(db: Session, admin_id: str):
    """관리자 권한 검증"""
    admin = db.query(User).filter(User.id == admin_id).first()
    if not admin or admin.role != "admin":
        raise HTTPException(status_code=403, detail="Admin 권한이 필요합니다")
    return admin

# --- Endpoints ---

@router.get("/stats/kpi", response_model=KPISummary)
def get_kpi_summary(db: Session = Depends(get_db)):
    """대시보드 상단 KPI 데이터"""
    total_agents = db.query(User).filter(User.role == "agent").count()
    total_vips = db.query(User).filter(User.role == "vip").count()
    
    # 예상 수익 계산 (단순화: 에이전트 구독 타입에 따른 합계)
    # 실제로는 구독 기록 테이블이 따로 있는 것이 좋으나 현재는 User 모델 필드 기준
    # 월간 ₩50,000, 연간 ₩500,000 가정
    revenue = 0
    agents = db.query(User).filter(User.role == "agent", User.subscription_status == "active").all()
    for agent in agents:
        if agent.subscription_type == "monthly":
            revenue += 50000
        elif agent.subscription_type == "yearly":
            revenue += 500000 // 12  # 월 평균
    
    pending_apps = db.query(AgentApplication).filter(AgentApplication.status == "pending").count()
    pending_solutions = db.query(SolutionRequest).filter(SolutionRequest.status == "pending").count()
    
    return {
        "total_agents": total_agents,
        "total_vips": total_vips,
        "expected_revenue": revenue,
        "pending_notifications": pending_apps + pending_solutions,
        "agent_growth_rate": 12.5, # Mock data for now
        "vip_growth_rate": 8.2     # Mock data for now
    }

@router.get("/stats/realtime", response_model=RealtimeStats)
def get_realtime_stats(db: Session = Depends(get_db)):
    """우측 사이드바 실시간 현황"""
    today = datetime.now().date()
    today_start = datetime.combine(today, datetime.min.time())
    
    new_agents = db.query(User).filter(User.role == "agent", User.created_at >= today_start).count()
    new_vips = db.query(User).filter(User.role == "vip", User.created_at >= today_start).count()
    
    return {
        "today_new_agents": new_agents,
        "today_new_vips": new_vips,
        "weekly_completed_deals": 47, # Mock
        "monthly_withdrawal_points": 8450000 # Mock
    }

@router.get("/agents")
def list_agents(db: Session = Depends(get_db), status: Optional[str] = None):
    """에이전트 목록 조회"""
    query = db.query(User).filter(User.role == "agent")
    if status:
        query = query.filter(User.subscription_status == status)
    
    agents = query.all()
    return [
        {
            "id": a.id,
            "name": a.name,
            "email": a.email,
            "subscription_status": a.subscription_status,
            "vip_limit": a.vip_limit,
            "points": a.points,
            "vip_count": db.query(User).filter(User.role == "vip", User.created_by == a.id).count(),
            "created_at": a.created_at
        } for a in agents
    ]

@router.put("/agents/{agent_id}")
def update_agent(agent_id: str, req: AgentUpdateRequest, db: Session = Depends(get_db)):
    """에이전트 정보 수정"""
    agent = db.query(User).filter(User.id == agent_id, User.role == "agent").first()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    
    if req.name: agent.name = req.name
    if req.email: agent.email = req.email
    if req.vip_limit is not None: agent.vip_limit = req.vip_limit
    if req.memo is not None: agent.memo = req.memo
    
    db.commit()
    return {"message": "Updated successfully"}

@router.delete("/agents/{agent_id}")
def delete_agent(agent_id: str, db: Session = Depends(get_db)):
    """에이전트 삭제 (데이터베이스 및 Supabase Auth 동기화)"""
    agent = db.query(User).filter(User.id == agent_id, User.role == "agent").first()
    if not agent:
        raise HTTPException(status_code=404, detail="에이전트를 찾을 수 없습니다.")
    
    # 관리 중인 VIP 확인
    vip_count = db.query(User).filter(User.role == "vip", User.created_by == agent_id).count()
    
    try:
        # 1. Supabase Auth에서 삭제 (관리자 권한)
        supabase = get_supabase_admin()
        
        # ID로 직접 삭제 시도 전에 이메일로 검색하여 확실한 Auth ID 확보
        # auth.admin.list_users()를 통해 이메일 검색 (약간의 오버헤드 있으나 가장 확실함)
        # response.users를 직접 순회해야 함 (list_users()는 객체를 반환)
        response = supabase.auth.admin.list_users()
        target_auth_id = None
        for u in response.users:
            if u.email == agent.email:
                target_auth_id = u.id
                break
        
        if target_auth_id:
            supabase.auth.admin.delete_user(target_auth_id)
            logger.info(f"Supabase Auth user deleted by email ({agent.email}): {target_auth_id}")
        else:
            # 검색 안되면 기존 ID로 최종 시도
            supabase.auth.admin.delete_user(agent_id)
            logger.info(f"Supabase Auth user deleted by ID directly: {agent_id}")
            
    except Exception as e:
        logger.error(f"Critical failure deleting Supabase Auth user: {str(e)}")
        # 사용자에게 에러를 알리는 것이 안전함 (삭제가 안되면 재가입이 안되므로)
        raise HTTPException(status_code=500, detail=f"인증 서버 계정 삭제에 실패했습니다: {str(e)}")

    # 2. 초대 토큰 삭제
    db.query(InvitationToken).filter(InvitationToken.user_id == agent_id).delete()

    # 3. 로컬 데이터베이스 삭제
    db.delete(agent)
    db.commit()
    return {"message": "에이전트와 인증 계정이 완전히 삭제되었습니다.", "affected_vips": vip_count}

from app.supabase_client import get_supabase_admin
from app.utils.mailer import send_email, send_vip_invite

import logging
logger = logging.getLogger(__name__)

@router.post("/agents/{agent_id}/reset-password")
def reset_agent_password(agent_id: str, db: Session = Depends(get_db)):
    """에이전트 비밀번호 초기화 메일 발송"""
    agent = db.query(User).filter(User.id == agent_id).first()
    if not agent:
        raise HTTPException(status_code=404, detail="에이전트를 찾을 수 없습니다.")
    
    # Supabase Auth를 통해 실제 재설정 메일 발송 트리거
    try:
        supabase = get_supabase_admin()
        # Supabase Auth 서비스 호출
        supabase.auth.reset_password_for_email(agent.email)
        return {"message": "이메일이 발송되었습니다.", "email": agent.email}
    except Exception as e:
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"Password reset email failed for {agent.email}: {str(e)}")
        raise HTTPException(status_code=500, detail="이메일 발송에 실패했습니다. 다시 시도해주세요")

@router.post("/agents/{agent_id}/points")
def adjust_agent_points(agent_id: str, req: PointAdjustRequest, db: Session = Depends(get_db)):
    """에이전트 포인트 추가/차감"""
    agent = db.query(User).filter(User.id == agent_id).first()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    
    if req.type == "add":
        agent.points += req.amount
    elif req.type == "deduct":
        if agent.points < req.amount:
            raise HTTPException(status_code=400, detail="Insufficient points")
        agent.points -= req.amount
    
    # 이력 기록
    transaction = PointTransaction(
        id=str(uuid.uuid4()),
        user_id=agent_id,
        amount=req.amount,
        type=req.type,
        reason=req.reason
    )
    db.add(transaction)
    db.commit()
    return {"message": "Points adjusted successfully", "current_points": agent.points}

@router.get("/vips")
def list_vips(db: Session = Depends(get_db)):
    """VIP 목록 조회"""
    vips = db.query(User).filter(User.role == "vip").all()
    return [
        {
            "id": v.id,
            "name": v.name,
            "email": v.email,
            "created_at": v.created_at
        } for v in vips
    ]

@router.delete("/vips/{vip_id}")
def delete_vip_hard(vip_id: str, db: Session = Depends(get_db)):
    """VIP 완전 삭제 (데이터베이스 및 Supabase Auth 동기화)"""
    vip = db.query(User).filter(User.id == vip_id, User.role == "vip").first()
    if not vip:
        raise HTTPException(status_code=404, detail="VIP를 찾을 수 없습니다.")
    
    try:
        # 1. Supabase Auth에서 삭제
        supabase = get_supabase_admin()
        
        # 이메일로 검색하여 확실한 Auth ID 확보
        response = supabase.auth.admin.list_users()
        target_auth_id = None
        for u in response.users:
            if u.email == vip.email:
                target_auth_id = u.id
                break
        
        if target_auth_id:
            supabase.auth.admin.delete_user(target_auth_id)
            logger.info(f"Supabase Auth VIP deleted by email ({vip.email}): {target_auth_id}")
        else:
            supabase.auth.admin.delete_user(vip_id)
            logger.info(f"Supabase Auth VIP deleted by ID directly: {vip_id}")
            
    except Exception as e:
        logger.error(f"Critical failure deleting Supabase Auth VIP: {str(e)}")
        raise HTTPException(status_code=500, detail=f"인증 서버 VIP 계정 삭제에 실패했습니다: {str(e)}")

    # 2. 연관 데이터 삭제
    db.query(Quest).filter(Quest.vip_id == vip_id).delete()
    db.query(HealthIndex).filter(HealthIndex.vip_id == vip_id).delete()
    db.query(Report).filter(Report.user_id == vip_id).delete()
    db.query(SolutionRequest).filter(SolutionRequest.vip_id == vip_id).delete()
    
    # 3. 초대 토큰 삭제
    db.query(InvitationToken).filter(InvitationToken.user_id == vip_id).delete()
    
    # 4. 로컬 유저 삭제 및 에이전트 카운트 감소
    agent_id = vip.created_by
    db.delete(vip)
    
    if agent_id:
        agent = db.query(User).filter(User.id == agent_id).first()
        if agent and agent.vip_current_count > 0:
            agent.vip_current_count -= 1

    db.commit()
    return {"message": "VIP와 인증 계정이 완전히 삭제되었습니다. 이제 재가입이 가능합니다."}

@router.get("/applications")
def list_applications(db: Session = Depends(get_db), status: str = "pending"):
    """에이전트 신청 목록"""
    apps = db.query(AgentApplication).filter(AgentApplication.status == status).all()
    return [
        {
            "id": a.id,
            "name": a.name,
            "email": a.email,
            "experience": a.experience,
            "status": a.status,
            "created_at": a.created_at
        } for a in apps
    ]

@router.post("/applications/{app_id}/approve")
def approve_application(app_id: str, db: Session = Depends(get_db)):
    """에이전트 신청 승인"""
    application = db.query(AgentApplication).filter(AgentApplication.id == app_id).first()
    if not application:
        raise HTTPException(status_code=404, detail="Application not found")
    
    application.status = "approved"
    
    # 새로운 에이전트 유저 생성 (또는 기존 유저 업데이트)
    # 실제 구현에서는 유저가 먼저 가입하고 나중에 신청하는 프로세스인지 확인 필요
    # 여기서는 신청 이메일로 매칭되는 유저가 있다고 가정하거나 새로 생성
    user = db.query(User).filter(User.email == application.email).first()
    if user:
        user.role = "agent"
        user.subscription_status = "active"
    
    # 실제 메일 발송
    subject = "[UNIFLOW] 에이전트 가입 신청이 승인되었습니다!"
    body = f"""
    <div style="font-family: sans-serif; max-width: 600px; margin: 0 auto; padding: 20px;">
        <h2>축하드립니다, {application.name}님!</h2>
        <p>유니플로우 에이전트 가입 신청이 승인되었습니다.</p>
        <p>이제 대시보드에서 모든 기능을 이용하실 수 있습니다.</p>
        <div style="margin: 30px 0;">
            <a href="https://uniflow.ai.kr/login" style="background-color: #000; color: #fff; padding: 12px 20px; text-decoration: none; border-radius: 5px;">로그인하기</a>
        </div>
    </div>
    """
    send_email(application.email, subject, body)
    
    db.commit()
    return {"message": "이메일이 발송되었습니다."}

@router.get("/solutions")
def list_solutions(db: Session = Depends(get_db), status: str = "pending"):
    """솔루션 요청 목록"""
    solutions = db.query(SolutionRequest).filter(SolutionRequest.status == status).all()
    return [
        {
            "id": s.id,
            "vip_id": s.vip_id,
            "service_type": s.service_type,
            "content": s.content,
            "status": s.status,
            "created_at": s.created_at
        } for s in solutions
    ]

@router.post("/notifications/send")
def send_notification(title: str, content: str, target: str, db: Session = Depends(get_db)):
    """공지사항 발송"""
    notif_id = str(uuid.uuid4())
    new_notif = Notification(
        id=notif_id,
        title=title,
        content=content,
        target=target
    )
    db.add(new_notif)
    
    # 대상 사용자들에게 개별 알림 생성
    users_query = db.query(User)
    if target != "all":
        users_query = users_query.filter(User.role == target)
    
    target_users = users_query.all()
    for user in target_users:
        db.add(UserNotification(
            id=str(uuid.uuid4()),
            user_id=user.id,
            notification_id=notif_id
        ))
    
    db.commit()
    return {"message": f"Sent notification to {len(target_users)} users"}

class AgentRegisterAndInviteRequest(BaseModel):
    name: str
    email: str
    phone: Optional[str] = None
    vip_limit: int = 5
    tier: str = "free" # free, paid
    memo: Optional[str] = None
    admin_id: str

@router.post("/agents/register-and-invite")
def register_and_invite_agent(req: AgentRegisterAndInviteRequest, db: Session = Depends(get_db)):
    """에이전트 등록 및 초대 (통합 프로세스 Step 1 & 2)"""
    # 1. 중복 확인
    existing_user = db.query(User).filter(User.email == req.email).first()
    if existing_user:
        raise HTTPException(status_code=400, detail="이미 등록된 이메일입니다.")
    
    # 2. 에이전트 레코드 생성 (상태: pending)
    agent_id = str(uuid.uuid4())
    
    # 등급별 한도 설정
    vip_limit = req.vip_limit
    if req.tier == "core_member":
        vip_limit = 999999
    elif req.tier == "monthly" or req.tier == "yearly":
        vip_limit = 50
    else:
        vip_limit = 5
        
    new_agent = User(
        id=agent_id,
        name=req.name,
        email=req.email,
        phone=req.phone,
        role="agent",
        tier=req.tier,
        subscription_status="active" if req.tier == "core_member" else "trial",
        vip_limit=vip_limit,
        memo=req.memo,
        id_status="pending", # 초대 대기 상태
        created_by=req.admin_id
    )
    
    # 체험판 날짜 설정 (에이전트 가입 시점이 아닌 등록 시점부터 시작하도록 유도 가능하나, 활성값은 auth.py에서 설정)
    if req.tier == "free":
        new_agent.trial_start_date = datetime.now()
        new_agent.trial_end_date = datetime.now() + timedelta(days=3)
        new_agent.subscription_status = "trial"

    db.add(new_agent)
    
    # 3. 초대 토큰 생성
    token_str = str(uuid.uuid4()).replace("-", "")
    new_token = InvitationToken(
        id=str(uuid.uuid4()),
        token=token_str,
        user_id=agent_id,
        email=req.email,
        expires_at=datetime.now() + timedelta(days=7)
    )
    db.add(new_token)
    
    # 4. 초대 이메일 발송
    settings = get_settings()
    # activation_link = f"{settings.frontend_url}/agent/activate?token={token_str}"
    # 유저의 요청 형식에 맞춤: https://uniflow.ai.kr/agent/activate?token={토큰}
    activation_link = f"https://uniflow.ai.kr/agent/activate?token={token_str}"
    
    subject = "[UNIFLOW] 에이전트 초대장"
    body = f"""
    <div style="font-family: sans-serif; max-width: 600px; margin: 0 auto; padding: 20px; border: 1px solid #eee; border-radius: 10px;">
        <h2 style="color: #333;">안녕하세요, {req.name}님!</h2>
        <p>비즈니스 성장 파트너 <b>UNIFLOW</b> 에이전트로 초대되었습니다.</p>
        <p>아래 버튼을 클릭하여 비밀번호를 설정하고 계정을 활성화해 주세요.</p>
        <div style="text-align: center; margin: 30px 0;">
            <a href="{activation_link}" style="background-color: #000; color: #fff; padding: 15px 25px; text-decoration: none; border-radius: 5px; font-weight: bold;">계정 활성화 및 시작하기</a>
        </div>
        <p style="color: #666; font-size: 13px;">※ 본 초대장은 발송 후 7일간 유효합니다.</p>
        <p style="color: #666; font-size: 13px;">※ 링크를 분실하셨다면 관리자에게 재발송을 요청하세요.</p>
    </div>
    """
    
    success = send_email(req.email, subject, body)
    
    if success:
        db.commit()
        return {
            "message": "에이전트가 등록되었고 초대 이메일이 발송되었습니다.",
            "status": "pending",
            "agent_id": agent_id,
            "token": token_str
        }
    else:
        logger.error(f"Failed to send unified invite to {req.email}")
        raise HTTPException(status_code=500, detail="이메일 발송에 실패했습니다. 다시 시도해주세요")

@router.post("/agents/{agent_id}/re-invite")
def re_invite_agent(agent_id: str, db: Session = Depends(get_db)):
    """에이전트 초대 링크 재발송"""
    agent = db.query(User).filter(User.id == agent_id, User.role == "agent").first()
    if not agent:
        raise HTTPException(status_code=404, detail="에이전트를 찾을 수 없습니다.")
    
    # 1. 기존 사용되지 않은 토큰 무효화
    db.query(InvitationToken).filter(
        InvitationToken.user_id == agent_id, 
        InvitationToken.used == False
    ).update({"expired": True})
    
    # 2. 새 토큰 생성
    token_str = str(uuid.uuid4()).replace("-", "")
    new_token = InvitationToken(
        id=str(uuid.uuid4()),
        token=token_str,
        user_id=agent_id,
        email=agent.email,
        expires_at=datetime.now() + timedelta(days=7)
    )
    db.add(new_token)
    
    # 3. 발송 시각 업데이트 및 상태 리셋
    agent.invitation_sent_at = datetime.now()
    if agent.status == "expired":
        agent.status = "pending"
    
    # 4. 재발송 이메일 전송
    activation_link = f"https://uniflow.ai.kr/agent/activate?token={token_str}"
    subject = "[UNIFLOW] 에이전트 초대 링크 재발송"
    body = f"""
    <div style="font-family: sans-serif; max-width: 600px; margin: 0 auto; padding: 20px; border: 1px solid #eee; border-radius: 10px;">
        <h2 style="color: #333;">안녕하세요, {agent.name}님!</h2>
        <p>요청하신 <b>UNIFLOW</b> 에이전트 초대 링크를 재발송해 드립니다.</p>
        <p>아래 버튼을 클릭하여 계정 활성화를 완료해 주세요.</p>
        <div style="text-align: center; margin: 30px 0;">
            <a href="{activation_link}" style="background-color: #000; color: #fff; padding: 15px 25px; text-decoration: none; border-radius: 5px; font-weight: bold;">초대 수락 및 시작하기</a>
        </div>
        <p style="color: #d9534f; font-size: 13px;">※ 이전 링크는 무효화되었습니다.</p>
        <p style="color: #666; font-size: 13px;">※ 새 링크는 발송 후 7일간 유효합니다.</p>
    </div>
    """
    
    success = send_email(agent.email, subject, body)
    if success:
        db.commit()
        return {"message": f"{agent.name}님에게 초대 링크가 재발송되었습니다."}
    else:
        raise HTTPException(status_code=500, detail="이메일 발송에 실패했습니다.")

# validate_invitation은 auth.py로 이동함 (로그인 전 단계이므로)

@router.post("/agents/{agent_id}/set-core-member")
def set_core_member(agent_id: str, db: Session = Depends(get_db)):
    """에이전트에게 코어 멤버 등급 부여 (무기한/무제한)"""
    agent = db.query(User).filter(User.id == agent_id, User.role == "agent").first()
    if not agent:
        raise HTTPException(status_code=404, detail="에이전트를 찾을 수 없습니다.")
    
    agent.tier = "core_member"
    agent.subscription_status = "lifetime"
    agent.subscription_end_date = None
    agent.trial_end_date = None
    agent.vip_limit = 999999
    
    db.commit()
    return {"message": f"{agent.name}님을 코어 멤버로 등록했습니다.", "tier": "core_member"}

@router.get("/agents/expiring-soon")
def list_expiring_soon(db: Session = Depends(get_db)):
    """만료 임박(3일 이내) 에이전트 목록 조회"""
    now = datetime.now()
    three_days_later = now + timedelta(days=3)
    
    # 체험 종료 임박 또는 구독 종료 임박
    expiring_agents = db.query(User).filter(
        User.role == "agent",
        (
            (User.subscription_status == "trial") & (User.trial_end_date <= three_days_later) |
            (User.subscription_status == "active") & (User.subscription_end_date <= three_days_later)
        )
    ).all()
    
    return [
        {
            "id": a.id,
            "name": a.name,
            "email": a.email,
            "tier": a.tier,
            "status": a.subscription_status,
            "expires_at": a.trial_end_date if a.subscription_status == "trial" else a.subscription_end_date
        } for a in expiring_agents
    ]

@router.patch("/solutions/{solution_id}")
def update_solution_status(solution_id: str, req: SolutionStatusUpdateRequest, db: Session = Depends(get_db)):
    """솔루션 요청 상태 변경 및 히스토리 기록"""
    solution = db.query(SolutionRequest).filter(SolutionRequest.id == solution_id).first()
    if not solution:
        raise HTTPException(status_code=404, detail="Solution request not found")
        
    old_status = solution.status
    solution.status = req.status
    if req.memo:
        solution.processing_memo = req.memo
    if req.processing_type:
        solution.processing_type = req.processing_type
        
    # 히스토리 기록
    history = SolutionHistory(
        id=str(uuid.uuid4()),
        request_id=solution_id,
        status=req.status,
        memo=req.memo,
        created_by=req.admin_id
    )
    db.add(history)
    
    # VIP에게 상태 변경 알람 메일 발송
    vip = db.query(User).filter(User.id == solution.vip_id).first()
    if vip and vip.email:
        subject = f"[UNIFLOW] 요청하신 솔루션의 상태가 [{req.status}]로 변경되었습니다."
        body = f"""
        <div style="font-family: sans-serif; max-width: 600px; margin: 0 auto; padding: 20px;">
            <h2>안녕하세요, {vip.name}님!</h2>
            <p>요청하신 솔루션의 처리 상태가 업데이트되었습니다.</p>
            <p><b>상태:</b> {req.status}</p>
            {f'<p><b>메모:</b> {req.memo}</p>' if req.memo else ''}
            <div style="margin: 30px 0;">
                <a href="https://uniflow.ai.kr/dashboard" style="background-color: #000; color: #fff; padding: 12px 20px; text-decoration: none; border-radius: 5px;">대시보드에서 확인하기</a>
            </div>
        </div>
        """
        send_email(vip.email, subject, body)
        
    db.commit()
    return {"message": "이메일이 발송되었습니다.", "status": req.status}

# --- 정산 관리 (Settlements) ---

@router.get("/settlements")
def list_settlements(db: Session = Depends(get_db)):
    """출금 신청 목록 및 요약"""
    pending = db.query(WithdrawalRequest).filter(WithdrawalRequest.status == "pending").all()
    approved = db.query(WithdrawalRequest).filter(WithdrawalRequest.status == "approved").all()
    paid = db.query(WithdrawalRequest).filter(
        WithdrawalRequest.status == "paid",
        WithdrawalRequest.processed_at >= datetime.now().replace(day=1) # 이번 달 지급분
    ).all()
    
    return {
        "pending": [
            {
                "id": r.id,
                "user_id": r.user_id,
                "user_name": db.query(User.name).filter(User.id == r.user_id).scalar(),
                "amount": r.amount,
                "net_amount": int(r.amount * 0.967), # 3.3% 원천징수
                "bank": r.bank_name,
                "account": r.account_number,
                "created_at": r.created_at
            } for r in pending
        ],
        "approved": [
            {
                "id": r.id,
                "user_id": r.user_id,
                "user_name": db.query(User.name).filter(User.id == r.user_id).scalar(),
                "amount": r.amount,
                "net_amount": int(r.amount * 0.967),
                "scheduled_date": (datetime.now() + timedelta(days=20)).replace(day=10).strftime("%Y-%m-%d") # 다음 10일
            } for r in approved
        ],
        "totals": {
            "pending_count": len(pending),
            "approved_amount": sum(r.amount for r in approved),
            "paid_this_month": sum(r.amount for r in paid)
        }
    }

@router.post("/settlements/{request_id}/status")
def update_settlement_status(request_id: str, req: SettlementStatusUpdate, db: Session = Depends(get_db)):
    """출금 신청 승인/거부/지급완료"""
    request = db.query(WithdrawalRequest).filter(WithdrawalRequest.id == request_id).first()
    if not request:
        raise HTTPException(status_code=404, detail="Request not found")
    
    request.status = req.status
    if req.memo:
        request.memo = req.memo
    
    if req.status == "paid":
        request.processed_at = datetime.now()
    
    db.commit()
    return {"message": f"Status updated to {req.status}"}

# --- 통계 (Stats) ---

@router.get("/stats/full")
def get_full_stats(db: Session = Depends(get_db)):
    """고급 통계 데이터 (차트용)"""
    # 1. 가입자 통계 (최근 7일)
    today = datetime.now().date()
    subscriber_stats = []
    for i in range(6, -1, -1):
        date = today - timedelta(days=i)
        start = datetime.combine(date, datetime.min.time())
        end = datetime.combine(date, datetime.max.time())
        count = db.query(User).filter(User.created_at.between(start, end)).count()
        subscriber_stats.append({"date": date.strftime("%m-%d"), "count": count})
    
    # 2. 수익 통계 (유료 결제자군)
    paid_agents = db.query(User).filter(User.role == "agent", User.subscription_status == "active").count()
    free_agents = db.query(User).filter(User.role == "agent", User.subscription_status == "free").count()
    conversion_rate = (paid_agents / (paid_agents + free_agents) * 100) if (paid_agents + free_agents) > 0 else 0
    
    # 3. VIP 활동도
    total_quests = db.query(Quest).count()
    completed_quests = db.query(Quest).filter(Quest.status == "completed").count()
    quest_rate = (completed_quests / total_quests * 100) if total_quests > 0 else 0
    
    return {
        "subscribers": subscriber_stats,
        "revenue": {
            "paid": paid_agents,
            "free": free_agents,
            "conversion_rate": round(conversion_rate, 1)
        },
        "activity": {
            "quest_completion_rate": round(quest_rate, 1),
            "active_vips": db.query(User).filter(User.role == "vip").count() # Mocking 'active' as total for now
        },
        "top_agents": [
            {
                "name": u.name,
                "vip_count": db.query(User).filter(User.role == "vip", User.created_by == u.id).count()
            } for u in db.query(User).filter(User.role == "agent").order_by(func.random()).limit(5)
        ]
    }

# --- 비회원 세션 결제 (Session Payments) ---

@router.get("/session-payments")
def list_session_payments(db: Session = Depends(get_db)):
    """비회원 세션 결제 목록 조회"""
    payments = db.query(SessionPayment).order_by(SessionPayment.created_at.desc()).all()
    return payments

@router.patch("/session-payments/{payment_id}")
def update_session_payment(payment_id: str, req: SessionPaymentUpdate, db: Session = Depends(get_db)):
    """비회원 세션 결제 상태/날짜 수정"""
    payment = db.query(SessionPayment).filter(SessionPayment.id == payment_id).first()
    if not payment:
        raise HTTPException(status_code=404, detail="Payment record not found")
    
    payment.payment_status = req.payment_status
    if req.session_date:
        payment.session_date = req.session_date
    
    db.commit()
    return {"message": "Updated successfully"}

# --- 신규 어드민 관리 API ---

@router.patch("/agents/{id}/tier")
def update_agent_tier(id: str, req: TierUpdateRequest, db: Session = Depends(get_db)):
    """에이전트 등급 변경 및 관련 설정 자동 업데이트"""
    verify_admin(db, req.admin_id)
    agent = db.query(User).filter(User.id == id, User.role == "agent").first()
    if not agent:
        raise HTTPException(status_code=404, detail="에이전트를 찾을 수 없습니다.")

    old_state = {"tier": agent.tier, "vip_limit": agent.vip_limit, "status": agent.subscription_status}
    now = datetime.now()

    if req.tier == "free":
        agent.subscription_status = "trial"
        agent.trial_start_date = now
        agent.trial_end_date = now + timedelta(days=3)
        agent.subscription_end_date = None
        agent.vip_limit = 5
    elif req.tier == "monthly":
        agent.subscription_status = "active"
        agent.subscription_start_date = now
        agent.subscription_end_date = now + timedelta(days=30)
        agent.trial_end_date = None
        agent.vip_limit = 50
    elif req.tier == "yearly":
        agent.subscription_status = "active"
        agent.subscription_start_date = now
        agent.subscription_end_date = now + timedelta(days=365)
        agent.trial_end_date = None
        agent.vip_limit = 50
    elif req.tier == "core_member":
        agent.subscription_status = "lifetime"
        agent.subscription_start_date = now
        agent.subscription_end_date = None
        agent.trial_end_date = None
        agent.vip_limit = 999999
        agent.grace_period_end_date = None
    else:
        raise HTTPException(status_code=400, detail="유효하지 않은 등급입니다.")

    agent.tier = req.tier
    log_admin_action(db, req.admin_id, "tier_change", id, old_state, {"tier": agent.tier})
    db.commit()
    return {"success": True, "message": "등급이 변경되었습니다", "agent": {"id": agent.id, "tier": agent.tier, "status": agent.subscription_status}}

@router.patch("/agents/{id}/status")
def update_agent_status(id: str, req: StatusUpdateRequest, db: Session = Depends(get_db)):
    """에이전트 구독 상태 직접 변경"""
    verify_admin(db, req.admin_id)
    agent = db.query(User).filter(User.id == id, User.role == "agent").first()
    if not agent:
        raise HTTPException(status_code=404, detail="에이전트를 찾을 수 없습니다.")

    old_status = agent.subscription_status
    agent.subscription_status = req.subscription_status
    now = datetime.now()

    if req.subscription_status == "active":
        if not agent.subscription_end_date or agent.subscription_end_date < now:
            # 과거면 등급에 맞춰 연장 (기본 30일)
            days = 365 if agent.tier == "yearly" else 30
            agent.subscription_end_date = now + timedelta(days=days)
        agent.grace_period_end_date = None
    elif req.subscription_status == "expired":
        agent.grace_period_end_date = now + timedelta(days=7)
    elif req.subscription_status == "lifetime":
        agent.subscription_end_date = None
        agent.tier = "core_member"

    log_admin_action(db, req.admin_id, "status_change", id, old_status, req.subscription_status)
    db.commit()
    return {"success": True, "message": "상태가 변경되었습니다", "agent": {"id": agent.id, "status": agent.subscription_status}}

@router.patch("/agents/{id}/extend")
def extend_subscription(id: str, req: ExtensionRequest, db: Session = Depends(get_db)):
    """에이전트 만료일 수동 연장"""
    verify_admin(db, req.admin_id)
    agent = db.query(User).filter(User.id == id, User.role == "agent").first()
    if not agent:
        raise HTTPException(status_code=404, detail="에이전트를 찾을 수 없습니다.")

    old_date = agent.subscription_end_date
    
    if req.subscription_end_date:
        agent.subscription_end_date = datetime.fromisoformat(req.subscription_end_date)
    elif req.days:
        base_date = agent.subscription_end_date if agent.subscription_end_date and agent.subscription_end_date > datetime.now() else datetime.now()
        agent.subscription_end_date = base_date + timedelta(days=req.days)
    else:
        raise HTTPException(status_code=400, detail="날짜 또는 일수를 입력해 주세요.")

    if agent.subscription_status == "expired":
        agent.subscription_status = "active"
    agent.grace_period_end_date = None

    log_admin_action(db, req.admin_id, "extend", id, old_date, agent.subscription_end_date)
    db.commit()
    return {"success": True, "message": "만료일이 연장되었습니다", "subscription_end_date": agent.subscription_end_date}

@router.patch("/agents/bulk-extend")
def bulk_extend_subscriptions(req: BulkExtensionRequest, db: Session = Depends(get_db)):
    """여러 에이전트의 만료일 동시 연장"""
    verify_admin(db, req.admin_id)
    
    agents = db.query(User).filter(User.id.in_(req.agent_ids), User.role == "agent").all()
    now = datetime.now()
    
    for agent in agents:
        base_date = agent.subscription_end_date if agent.subscription_end_date and agent.subscription_end_date > now else now
        agent.subscription_end_date = base_date + timedelta(days=req.days)
        
        if agent.subscription_status == "expired":
            agent.subscription_status = "active"
        agent.grace_period_end_date = None
        
        log_admin_action(db, req.admin_id, "bulk_extend", agent.id, None, f"+{req.days} days")

    db.commit()
    return {"success": True, "message": f"{len(agents)}명의 만료일이 연장되었습니다", "updated_count": len(agents)}

@router.patch("/agents/{id}")
def partial_update_agent(id: str, req: AgentPartialUpdateRequest, db: Session = Depends(get_db)):
    """에이전트 정보 통합 수정 (Partial Update)"""
    verify_admin(db, req.admin_id)
    agent = db.query(User).filter(User.id == id, User.role == "agent").first()
    if not agent:
        raise HTTPException(status_code=404, detail="에이전트를 찾을 수 없습니다.")

    old_data = {k: getattr(agent, k) for k in req.dict(exclude_unset=True).keys() if hasattr(agent, k)}
    
    if req.name: agent.name = req.name
    if req.vip_limit is not None: agent.vip_limit = req.vip_limit
    if req.subscription_end_date:
        agent.subscription_end_date = datetime.fromisoformat(req.subscription_end_date)
    
    # Tier 변경 시 로직 적용
    if req.tier and req.tier != agent.tier:
        # update_agent_tier 로직 재사용
        now = datetime.now()
        if req.tier == "free":
            agent.subscription_status = "trial"
            agent.vip_limit = 5
        elif req.tier in ["monthly", "yearly"]:
            agent.subscription_status = "active"
            agent.vip_limit = 50
        elif req.tier == "core_member":
            agent.subscription_status = "lifetime"
            agent.vip_limit = 999999
        agent.tier = req.tier

    if req.subscription_status:
        agent.subscription_status = req.subscription_status

    log_admin_action(db, req.admin_id, "profile_update", id, old_data, req.dict(exclude_unset=True))
    db.commit()
    return {"success": True, "message": "에이전트 정보가 수정되었습니다", "agent": {"id": agent.id, "name": agent.name, "tier": agent.tier, "status": agent.subscription_status}}
