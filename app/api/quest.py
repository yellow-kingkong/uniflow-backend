from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import func
from typing import List, Optional
from datetime import datetime
import uuid

from app.database import get_db
from app.models import User, Quest, HealthIndex, Notification
from app.agents.quest_agent import QuestAgent
from pydantic import BaseModel

router = APIRouter(tags=["quests"])
agent = QuestAgent()

# --- Schemas ---

class EvaluateRequest(BaseModel):
    checkedIndexes: List[int] # Lovable 프롬프트와 일치하도록 CamelCase 사용

# --- Endpoints ---

@router.get("/init")
def initialize_vip_quests(vip_id: str, db: Session = Depends(get_db)):
    """VIP 가입 시 초기 6개 지표 퀘스트 자동 생성"""
    vip = db.query(User).filter(User.id == vip_id).first()
    if not vip:
        raise HTTPException(status_code=404, detail="VIP not found")
        
    existing = db.query(Quest).filter(Quest.vip_id == vip_id).first()
    if existing:
        return {"message": "Quests already initialized"}

    latest_health = db.query(HealthIndex).filter(HealthIndex.vip_id == vip_id).order_by(HealthIndex.created_at.desc()).first()
    
    metrics = [
        ("future_safety_net", latest_health.asset_stability if latest_health else 50),
        ("emotional_anchor", latest_health.emotional_balance if latest_health else 50),
        ("time_mastery", latest_health.time_independence if latest_health else 50),
        ("body_signals", latest_health.physical_condition if latest_health else 50),
        ("relationship_power", latest_health.network_power if latest_health else 50),
        ("system_leverage", latest_health.system_leverage if latest_health else 50)
    ]
    
    sorted_metrics = sorted(metrics, key=lambda x: x[1])
    
    titles = {
        "future_safety_net": "자산 안정성 점검",
        "emotional_anchor": "정서 균형 점검",
        "time_mastery": "시간 독립성 점검",
        "body_signals": "신체 컨디션 점검",
        "relationship_power": "네트워크 파워 점검",
        "system_leverage": "시스템 레버리지 점검"
    }

    new_quests = []
    for i, (category, score) in enumerate(sorted_metrics):
        new_quest = Quest(
            id=str(uuid.uuid4()),
            vip_id=vip_id,
            agent_id=vip.created_by,
            title=titles.get(category, category),
            category=category,
            quest_order=i + 1,
            is_locked=(i != 0),
            status="pending"
        )
        db.add(new_quest)
        new_quests.append(new_quest)
        
    db.commit()
    return {"message": "Initialization success", "count": len(new_quests)}

@router.post("/{quest_id}/generate-questions")
def generate_quest_questions(quest_id: str, db: Session = Depends(get_db)):
    """퀘스트용 AI 체크리스트 생성"""
    quest = db.query(Quest).filter(Quest.id == quest_id).first()
    if not quest:
        raise HTTPException(status_code=404, detail="Quest not found")
    
    if quest.is_locked:
        raise HTTPException(status_code=403, detail="Quest is locked")

    vip = db.query(User).filter(User.id == quest.vip_id).first()
    latest_health = db.query(HealthIndex).filter(HealthIndex.vip_id == quest.vip_id).order_by(HealthIndex.created_at.desc()).first()
    
    category_to_field = {
        "future_safety_net": "asset_stability",
        "emotional_anchor": "emotional_balance",
        "time_mastery": "time_independence",
        "body_signals": "physical_condition",
        "relationship_power": "network_power",
        "system_leverage": "system_leverage"
    }
    field_name = category_to_field.get(quest.category, quest.category)
    score = getattr(latest_health, field_name) if latest_health and hasattr(latest_health, field_name) else 50

    ai_content = agent.generate_questions(vip.name, quest.category, score)
    
    quest.ai_questions = ai_content
    db.commit()
    
    return ai_content

@router.post("/{quest_id}/evaluate")
def evaluate_quest(quest_id: str, req: EvaluateRequest, db: Session = Depends(get_db)):
    """퀘스트 답변 평가 및 다음 단계 해제"""
    quest = db.query(Quest).filter(Quest.id == quest_id).first()
    if not quest:
        raise HTTPException(status_code=404, detail="Quest not found")
        
    if not quest.ai_questions:
        raise HTTPException(status_code=400, detail="Questions not generated yet")

    vip = db.query(User).filter(User.id == quest.vip_id).first()
    
    evaluation = agent.evaluate_answers(
        vip.name, 
        quest.category, 
        quest.ai_questions["checklist"], 
        req.checkedIndexes
    )
    
    quest.user_answers = req.checkedIndexes
    quest.checked_count = len(req.checkedIndexes)
    quest.ai_evaluation = evaluation
    
    if evaluation.get("passed"):
        quest.status = "completed"
        quest.completed_at = datetime.now()
        
        next_quest = db.query(Quest).filter(
            Quest.vip_id == quest.vip_id,
            Quest.quest_order == quest.quest_order + 1
        ).first()
        
        if next_quest:
            next_quest.is_locked = False
            
        new_noti = Notification(
            id=str(uuid.uuid4()),
            title=f"🎉 '{quest.title}' 미션 완료!",
            content=evaluation.get("message"),
            target="vip",
            created_by=quest.agent_id
        )
        db.add(new_noti)
        
    db.commit()
    return evaluation
