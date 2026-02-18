from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import func
from typing import List, Optional
from datetime import datetime
import uuid

from app.database import get_db
from app.models import User, HealthIndex, Quest, SolutionRequest, Notification, UserNotification, Report, AgentNote
from pydantic import BaseModel
from app.api.quest import initialize_vip_quests, generate_quest_questions, evaluate_quest, EvaluateRequest

router = APIRouter(tags=["vip"])

# --- Helper ---
def _get_current_quest(vip_id: str, db: Session):
    """지표 개선을 위해 현재 진행 중인(잠금 해제되었으나 완료되지 않은) 퀘스트를 찾음"""
    return db.query(Quest).filter(
        Quest.vip_id == vip_id,
        Quest.is_locked == False,
        Quest.status != "completed"
    ).order_by(Quest.quest_order.asc()).first()

# --- Schemas ---

class HealthIndexUpdate(BaseModel):
    asset_stability: int
    time_independence: int
    physical_condition: int
    emotional_balance: int
    network_power: int
    system_leverage: int

class SolutionRequestCreate(BaseModel):
    service_type: str
    content: str
    preferred_time: str

# --- Endpoints ---

@router.get("/dashboard/health")
def get_health_summary(vip_id: str, db: Session = Depends(get_db)):
    """VIP 건강 지표 요약 (차트용)"""
    latest = db.query(HealthIndex).filter(HealthIndex.vip_id == vip_id).order_by(HealthIndex.created_at.desc()).first()
    if not latest:
        # 기본값 리턴
        return {
            "asset_stability": 50,
            "time_independence": 50,
            "physical_condition": 50,
            "emotional_balance": 50,
            "network_power": 50,
            "system_leverage": 50,
            "overall_score": 50,
            "created_at": datetime.now()
        }
    return {
        "asset_stability": latest.asset_stability,
        "time_independence": latest.time_independence,
        "physical_condition": latest.physical_condition,
        "emotional_balance": latest.emotional_balance,
        "network_power": latest.network_power,
        "system_leverage": latest.system_leverage,
        "overall_score": latest.overall_score,
        "created_at": latest.created_at
    }

@router.get("/quests")
def list_quests(vip_id: str, status: Optional[str] = None, db: Session = Depends(get_db)):
    """퀘스트 목록 조회"""
    query = db.query(Quest).filter(Quest.vip_id == vip_id)
    if status == "completed":
        query = query.filter(Quest.status == "completed")
    elif status == "pending":
        query = query.filter(Quest.status != "completed")
    
    quests = query.all()
    
    # 퀘스트가 하나도 없으면 자동 초기화 시도
    if not quests:
        initialize_vip_quests(vip_id, db)
        quests = query.all()
        
    return [
        {
            "id": q.id,
            "title": q.title,
            "category": q.category,
            "status": q.status,
            "is_locked": q.is_locked,
            "quest_order": q.quest_order,
            "ai_questions": q.ai_questions,
            "ai_evaluation": q.ai_evaluation,
            "due_date": q.due_date
        } for q in quests
    ]

@router.post("/quests/{quest_id}/complete")
def complete_quest(quest_id: str, db: Session = Depends(get_db)):
    """퀘스트 완료 체크"""
    quest = db.query(Quest).filter(Quest.id == quest_id).first()
    if not quest:
        raise HTTPException(status_code=404, detail="Quest not found")
    
    quest.status = "completed"
    quest.completed_at = datetime.now()
    
    # 에이전트에게 알림 전송 로직 가능
    db.commit()
    return {"message": "Quest completed!"}

@router.post("/solution-request")
def create_solution_request(vip_id: str, req: SolutionRequestCreate, db: Session = Depends(get_db)):
    """솔루션 요청 전송"""
    vip = db.query(User).filter(User.id == vip_id).first()
    if not vip:
        raise HTTPException(status_code=404, detail="VIP not found")
    
    new_req = SolutionRequest(
        id=str(uuid.uuid4()),
        vip_id=vip_id,
        agent_id=vip.created_by,
        service_type=req.service_type,
        content=req.content,
        preferred_time=req.preferred_time,
        status="pending"
    )
    db.add(new_req)
    db.commit()
    return {"message": "Success"}

@router.get("/agent")
def get_agent_info(vip_id: str, db: Session = Depends(get_db)):
    """담당 에이전트 정보 조회"""
    vip = db.query(User).filter(User.id == vip_id).first()
    if not vip or not vip.created_by:
        return {"agent": None}
    
    agent = db.query(User).filter(User.id == vip.created_by).first()
    if not agent:
        return {"agent": None}
        
    return {
        "id": agent.id,
        "name": agent.name,
        "email": agent.email,
        "phone": agent.phone,
        "specialty": agent.specialty,
        "intro": agent.intro
    }

@router.get("/activities")
def get_vip_activities(vip_id: str, db: Session = Depends(get_db)):
    """에이전트 프로필용 VIP 활동 내역 집계"""
    report_count = db.query(Report).filter(Report.user_id == vip_id).count()
    note_count = db.query(AgentNote).filter(AgentNote.vip_id == vip_id).count()
    quest_count = db.query(Quest).filter(Quest.vip_id == vip_id, Quest.status == "completed").count()
    
    # 최근 활동 5개 추출
    recent_activities = []
    
    # 리포트
    reports = db.query(Report).filter(Report.user_id == vip_id).order_by(Report.created_at.desc()).limit(3).all()
    for r in reports:
        recent_activities.append({
            "type": "report",
            "title": r.title or "비즈니스 진단 리포트",
            "date": r.created_at
        })
        
    # 퀘스트
    quests = db.query(Quest).filter(Quest.vip_id == vip_id, Quest.status == "completed").order_by(Quest.completed_at.desc()).limit(3).all()
    for q in quests:
        recent_activities.append({
            "type": "quest",
            "title": q.title,
            "date": q.completed_at
        })
        
    # 지표 업데이트
    health_updates = db.query(HealthIndex).filter(HealthIndex.vip_id == vip_id).order_by(HealthIndex.created_at.desc()).limit(3).all()
    for h in health_updates:
        recent_activities.append({
            "type": "health",
            "title": "건강 지표 업데이트",
            "date": h.created_at
        })

    # 시간순 정렬
    recent_activities.sort(key=lambda x: x["date"], reverse=True)

    return {
        "stats": {
            "reports": report_count,
            "consultations": note_count,
            "quests": quest_count
        },
        "recent": recent_activities[:5]
    }

# --- Diagnosis Mapping Endpoints ---

@router.post("/diagnosis/start")
def diagnosis_start(vip_id: str, db: Session = Depends(get_db)):
    """진단 프로세스 시작 (퀘스트 초기화)"""
    return initialize_vip_quests(vip_id, db)

@router.get("/diagnosis/questions")
def diagnosis_questions(vip_id: str, db: Session = Depends(get_db)):
    """현재 단계의 진단 질문(체크리스트) 조회"""
    quest = _get_current_quest(vip_id, db)
    if not quest:
        raise HTTPException(status_code=404, detail="진행 중인 진단 항목이 없습니다.")
    return generate_quest_questions(quest.id, db)

@router.post("/diagnosis/answer")
def diagnosis_answer(vip_id: str, req: EvaluateRequest, db: Session = Depends(get_db)):
    """진단 답변 제출 및 평가"""
    quest = _get_current_quest(vip_id, db)
    if not quest:
        raise HTTPException(status_code=404, detail="진행 중인 진단 항목이 없습니다.")
    return evaluate_quest(quest.id, req, db)

@router.post("/diagnosis/complete")
def diagnosis_complete(vip_id: str, db: Session = Depends(get_db)):
    """현재 진단 단계 완료 처리"""
    quest = _get_current_quest(vip_id, db)
    if not quest:
        raise HTTPException(status_code=404, detail="마무리할 진단 항목이 없습니다.")
    
    quest.status = "completed"
    quest.completed_at = datetime.now()
    
    # 다음 퀘스트 잠금 해제 로직 (이미 evaluate_quest에서 처리하지만 수동 완료 대비)
    next_q = db.query(Quest).filter(
        Quest.vip_id == vip_id,
        Quest.quest_order == quest.quest_order + 1
    ).first()
    if next_q:
        next_q.is_locked = False
        
    db.commit()
    return {"message": "Step completed"}

@router.get("/report")
def get_diagnosis_report(vip_id: str, db: Session = Depends(get_db)):
    """전체 진단 결과(6축 시트) 조회"""
    return get_health_summary(vip_id, db)
