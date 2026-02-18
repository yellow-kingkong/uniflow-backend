from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
from datetime import datetime, timedelta
import logging

from app.database import get_db
from app.models import User, InvitationToken
from app.supabase_client import get_supabase_admin

router = APIRouter(tags=["auth"])

class FindIdRequest(BaseModel):
    name: str
    phone: str

class FindPasswordRequest(BaseModel):
    email: str

@router.post("/find-id")
def find_id(req: FindIdRequest, db: Session = Depends(get_db)):
    """이름과 전화번호로 아이디(이메일) 찾기"""
    user = db.query(User).filter(User.name == req.name, User.phone == req.phone).first()
    if not user:
        raise HTTPException(status_code=404, detail="일치하는 가입 정보가 없습니다.")
    
    # 이메일 마스킹 처리 (예: ab***@naver.com)
    email = user.email
    if "@" in email:
        local, domain = email.split("@")
        if len(local) > 2:
            masked_local = local[:2] + "*" * (len(local) - 2)
        else:
            masked_local = local[0] + "*"
        masked_email = f"{masked_local}@{domain}"
    else:
        masked_email = email[:2] + "***"
        
    return {"message": "아이디를 찾았습니다.", "masked_email": masked_email}

from app.supabase_client import get_supabase_admin

@router.post("/find-password")
def find_password(req: FindPasswordRequest, db: Session = Depends(get_db)):
    """비밀번호 찾기 (비밀번호 재설정 메일 발송)"""
    user = db.query(User).filter(User.email == req.email).first()
    if not user:
        raise HTTPException(status_code=404, detail="등록되지 않은 이메일입니다.")
    
    # Supabase Auth를 통해 실제 재설정 메일 발송 트리거
    try:
        supabase = get_supabase_admin()
        # supabase-py v2+ 규격
        res = supabase.auth.reset_password_for_email(req.email)
        return {
            "message": "비밀번호 재설정 안내 메일이 발송되었습니다. 메일함을 확인해 주세요.",
            "status": "success"
        }
    except Exception as e:
        logger = logging.getLogger(__name__)
        logger.error(f"Password reset failed for {req.email}: {str(e)}")
        raise HTTPException(status_code=500, detail="이메일 발송에 실패했습니다. 다시 시도해주세요")

# --- 에이전트 초대 및 계정 활성화 (통합 프로세스 Step 3 & 4) ---

@router.get("/invitation/validate/{token}")
def validate_invitation_token(token: str, db: Session = Depends(get_db)):
    """초대 토큰 유효성 검사"""
    inv = db.query(InvitationToken).filter(InvitationToken.token == token).first()
    
    if not inv:
        raise HTTPException(status_code=404, detail="유효하지 않은 초대 링크입니다.")
    
    if inv.used:
        raise HTTPException(status_code=400, detail="이미 활성화된 계정입니다. 로그인해 주세요.")
        
    if inv.expired or inv.expires_at < datetime.now():
        raise HTTPException(status_code=400, detail="만료된 초대 링크입니다. 관리자에게 재발송을 요청하세요.")
    
    # 해당 유저 정보 조회
    user = db.query(User).filter(User.id == inv.user_id).first()
    
    return {
        "email": inv.email,
        "name": user.name if user else "",
        "token": token
    }

class InvitationActivateRequest(BaseModel):
    token: str
    password: str

@router.post("/invitation/activate")
def activate_account(req: InvitationActivateRequest, db: Session = Depends(get_db)):
    """에이전트 계정 활성화 (Supabase Auth 계정 생성 및 상태 업데이트)"""
    # 1. 토큰 검증
    inv = db.query(InvitationToken).filter(InvitationToken.token == req.token).first()
    if not inv or inv.used or inv.expired or inv.expires_at < datetime.now():
        raise HTTPException(status_code=400, detail="유효하지 않거나 만료된 토큰입니다.")
        
    user = db.query(User).filter(User.id == inv.user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="연결된 사용자 정보를 찾을 수 없습니다.")

    # 2. Supabase Auth에 사용자 생성 (Admin 권한으로 강제 생성)
    try:
        supabase = get_supabase_admin()
        
        # 이미 Auth에 동일 이메일이 있는지 최종 확인 (정리 안 된 유령 계정 대비)
        auth_users = supabase.auth.admin.list_users()
        orphaned_auth_id = None
        for u in auth_users.users:
            if u.email == user.email:
                orphaned_auth_id = u.id
                break
        
        if orphaned_auth_id:
            logger.info(f"Cleaning up orphaned auth user during activation: {user.email}")
            supabase.auth.admin.delete_user(orphaned_auth_id)

        # 실제 계정 생성 (이메일 확인 절차 건너뜀 - 관리자가 신뢰한 초대이므로)
        auth_res = supabase.auth.admin.create_user({
            "email": user.email,
            "password": req.password,
            "email_confirm": True,
            "user_metadata": {
                "role": user.role,
                "name": user.name
            }
        })
        
        if not auth_res or not auth_res.user:
            raise Exception("Failed to create auth user record")
            
        new_auth_id = auth_res.user.id
        
        # 3. 로컬 DB 유저 상태 업데이트 및 가입 시점 기록
        user.id_status = "active" # 기존 필드명 status (id_status 매핑)
        user.auth_id = new_auth_id
        
        # 가입 시점에 체험판 시작일 갱신 (초대 시점이 아닌 가입 시점부터 3일 부여)
        if user.tier == "free":
            user.trial_start_date = datetime.now()
            user.trial_end_date = datetime.now() + timedelta(days=3)
            user.subscription_status = "trial"
            
        # VIP 가입 시 초대한 에이전트의 실시간 카운트 증가
        if user.role == "vip" and user.created_by:
            agent = db.query(User).filter(User.id == user.created_by).first()
            if agent:
                agent.vip_current_count = (agent.vip_current_count or 0) + 1
                logger.info(f"Incremented VIP count for agent {agent.email}: {agent.vip_current_count}")

        # 4. 토큰 사용 처리
        inv.used = True
        inv.used_at = datetime.now()
        
        db.commit()
        return {
            "message": "계정이 성공적으로 활성화되었습니다! 이제 로그인하실 수 있습니다.",
            "role": user.role,
            "email": user.email
        }
        
    except Exception as e:
        db.rollback()
        logger.error(f"Account activation failed for {user.email}: {str(e)}")
        raise HTTPException(status_code=500, detail=f"계정 활성화 중 오류가 발생했습니다: {str(e)}")
