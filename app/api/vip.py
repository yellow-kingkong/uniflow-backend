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

# 6축 비즈니스 진단 20개 고정 질문 (프론트엔드 diagnosisApi.ts와 연동)
DIAGNOSIS_QUESTIONS = [
    # 자산 안정성 (asset) - 3문항
    {"id": "asset_1", "question": "현재 월 순수익(수입 - 고정 지출)은 얼마나 됩니까?", "category": "asset", "type": "radio", "options": ["적자 또는 0원", "1~50만원", "50~200만원", "200만원 이상"], "order": 1},
    {"id": "asset_2", "question": "현재 6개월 이상 생활 가능한 비상금(비상 자금)을 보유하고 있습니까?", "category": "asset", "type": "radio", "options": ["없음", "1~3개월치", "3~6개월치", "6개월 이상"], "order": 2},
    {"id": "asset_3", "question": "부채(대출, 카드빚 등) 대비 자산 비율이 어떻게 됩니까?", "category": "asset", "type": "radio", "options": ["부채가 자산을 초과", "부채 = 자산의 50% 이상", "부채 = 자산의 30% 미만", "부채 없음"], "order": 3},
    # 시간 독립성 (time) - 3문항
    {"id": "time_1", "question": "하루 중 '내가 원하는 일'에 쓸 수 있는 자유 시간은?", "category": "time", "type": "radio", "options": ["1시간 미만", "1~3시간", "3~6시간", "6시간 이상"], "order": 4},
    {"id": "time_2", "question": "현재 비즈니스 운영이 나 없이도 하루 이상 돌아갈 수 있습니까?", "category": "time", "type": "radio", "options": ["전혀 안됨, 내가 없으면 멈춤", "몇 시간은 가능", "하루~이틀 가능", "1주일 이상 가능"], "order": 5},
    {"id": "time_3", "question": "반복적으로 하는 업무 중 자동화되어 있는 비율은?", "category": "time", "type": "radio", "options": ["10% 미만", "10~30%", "30~60%", "60% 이상"], "order": 6},
    # 신체 컨디션 (body) - 3문항
    {"id": "body_1", "question": "최근 한 달 기준, 규칙적인 운동(주 2회 이상)을 하고 있습니까?", "category": "body", "type": "radio", "options": ["전혀 안함", "월 1~3회", "주 1회", "주 2회 이상"], "order": 7},
    {"id": "body_2", "question": "현재 수면의 질과 평균 수면 시간은?", "category": "body", "type": "radio", "options": ["5시간 미만, 항상 피곤함", "5~6시간, 자주 피곤함", "6~7시간, 보통", "7~8시간, 개운함"], "order": 8},
    {"id": "body_3", "question": "현재 에너지 수준을 1~10으로 평가하면?", "category": "body", "type": "slider", "options": [], "order": 9},
    # 정서 균형 (emotion) - 4문항
    {"id": "emotion_1", "question": "비즈니스/삶에 대한 전반적인 만족도는?", "category": "emotion", "type": "slider", "options": [], "order": 10},
    {"id": "emotion_2", "question": "최근 번아웃(극도의 피로나 무기력)을 느낀 적이 있습니까?", "category": "emotion", "type": "radio", "options": ["거의 매일", "주 2~3회", "월 1~2회", "거의 없음"], "order": 11},
    {"id": "emotion_3", "question": "스트레스 상황에서 회복하는 데 보통 얼마나 걸립니까?", "category": "emotion", "type": "radio", "options": ["1주일 이상", "3~7일", "1~2일", "하루 이내"], "order": 12},
    {"id": "emotion_4", "question": "현재 가장 큰 정서적 걱정거리는? (복수 선택)", "category": "emotion", "type": "checkbox", "options": ["수입/재정 불안", "인간관계", "건강", "미래에 대한 불확실성", "없음"], "order": 13},
    # 네트워크 파워 (network) - 4문항
    {"id": "network_1", "question": "사업/커리어와 관련하여 적극적으로 연락 가능한 인맥 수는?", "category": "network", "type": "radio", "options": ["5명 미만", "5~20명", "20~50명", "50명 이상"], "order": 14},
    {"id": "network_2", "question": "최근 6개월 내 새로운 비즈니스 파트너 또는 협업 기회가 생겼습니까?", "category": "network", "type": "radio", "options": ["없음", "관심 표현 수준", "미팅 진행함", "실제 협업 중"], "order": 15},
    {"id": "network_3", "question": "나를 타인에게 소개해줄 수 있는 지인이 몇 명이나 됩니까?", "category": "network", "type": "radio", "options": ["1~2명", "3~5명", "6~10명", "11명 이상"], "order": 16},
    {"id": "network_4", "question": "온라인 또는 오프라인 커뮤니티/네트워크 활동을 하고 있습니까?", "category": "network", "type": "radio", "options": ["전혀 없음", "가끔 참여", "정기적으로 참여", "직접 운영 중"], "order": 17},
    # 시스템 레버리지 (system) - 3문항
    {"id": "system_1", "question": "현재 수익 구조에서 나의 시간을 쓰지 않고도 발생하는 수익(자동화/파시브 인컴)의 비율은?", "category": "system", "type": "radio", "options": ["0%", "1~10%", "10~30%", "30% 이상"], "order": 18},
    {"id": "system_2", "question": "현재 비즈니스에 표준 운영 절차(SOP) 또는 매뉴얼이 있습니까?", "category": "system", "type": "radio", "options": ["전혀 없음", "일부 있음", "주요 업무는 있음", "전 분야 문서화"], "order": 19},
    {"id": "system_3", "question": "현재 비즈니스의 확장 가능성을 어떻게 보십니까?", "category": "system", "type": "radio", "options": ["나 혼자 감당이 한계", "1~2명 더 추가 가능", "팀 구조로 성장 가능", "무한 확장 가능한 구조"], "order": 20},
]

# 점수 환산 테이블 (radio 답변 → 점수)
SCORE_MAP = {
    0: 15,   # 첫 번째 옵션: 15점
    1: 40,   # 두 번째 옵션: 40점
    2: 70,   # 세 번째 옵션: 70점
    3: 100,  # 네 번째 옵션: 100점
}

class DiagnosisStartRequest(BaseModel):
    vip_id: str

@router.post("/diagnosis/start")
def diagnosis_start(req: DiagnosisStartRequest, db: Session = Depends(get_db)):
    """진단 프로세스 시작"""
    vip_id = req.vip_id
    vip = db.query(User).filter(User.id == vip_id).first()
    if not vip:
        raise HTTPException(status_code=404, detail=f"VIP not found: {vip_id}")
    return {"diagnosis_id": vip_id}

@router.get("/diagnosis/questions")
def get_diagnosis_questions(diagnosis_id: Optional[str] = None):
    """6축 비즈니스 진단 질문 반환 (20개 고정)"""
    # diagnosis_id는 vip_id와 동일하게 사용됨
    return {"questions": DIAGNOSIS_QUESTIONS}

class DiagnosisAnswerRequest(BaseModel):
    diagnosis_id: str   # vip_id와 동일
    question_id: str
    answer: object      # str | int | list[str] 모두 허용

# 메모리 내 임시 저장소 (세션 기반 - 실제 운영 시 Redis 권장)
_diagnosis_sessions: dict = {}

@router.post("/diagnosis/answer")
def save_diagnosis_answer(req: DiagnosisAnswerRequest):
    """진단 답변 저장 (완료 시 health_index 업데이트 용으로 메모리에 임시 보관)"""
    vip_id = req.diagnosis_id
    if vip_id not in _diagnosis_sessions:
        _diagnosis_sessions[vip_id] = {}
    _diagnosis_sessions[vip_id][req.question_id] = req.answer
    return {"saved": True, "question_id": req.question_id}

class DiagnosisCompleteRequest(BaseModel):
    diagnosis_id: str   # vip_id와 동일

@router.post("/diagnosis/complete")
def complete_diagnosis(req: DiagnosisCompleteRequest, db: Session = Depends(get_db)):
    """진단 완료 - 답변을 집계하여 health_index 테이블 업데이트"""
    vip_id = req.diagnosis_id

    vip = db.query(User).filter(User.id == vip_id).first()
    if not vip:
        raise HTTPException(status_code=404, detail=f"VIP not found: {vip_id}")

    # 세션에서 답변 가져오기
    answers = _diagnosis_sessions.get(vip_id, {})

    def calc_score(q_id: str, question: dict) -> float:
        """질문 유형에 따라 0~100 점수 계산"""
        answer = answers.get(q_id)
        if answer is None:
            return 50.0  # 미응답 시 중간값

        q_type = question["type"]
        options = question.get("options", [])

        if q_type == "radio" and options:
            try:
                idx = options.index(str(answer))
                return float(SCORE_MAP.get(idx, 50))
            except ValueError:
                return 50.0

        elif q_type == "slider":
            # 슬라이더는 1~10 → 10~100 변환
            try:
                val = float(answer)
                return min(100.0, max(0.0, val * 10))
            except (TypeError, ValueError):
                return 50.0

        elif q_type == "checkbox" and options:
            # 체크한 항목 수에 따라 점수 계산
            selected = answer if isinstance(answer, list) else []
            if "없음" in selected:
                return 90.0  # 걱정거리 없음 = 높은 점수
            non_neutral = [s for s in selected if s != "없음"]
            if len(non_neutral) == 0:
                return 50.0
            penalty = len(non_neutral) * 20
            return max(10.0, 80.0 - penalty)

        return 50.0

    # 카테고리별 점수 계산
    cat_scores: dict[str, list[float]] = {
        "asset": [], "time": [], "body": [],
        "emotion": [], "network": [], "system": []
    }

    for q in DIAGNOSIS_QUESTIONS:
        cat = q["category"]
        score = calc_score(q["id"], q)
        if cat in cat_scores:
            cat_scores[cat].append(score)

    # 카테고리별 평균
    def avg(lst):
        return round(sum(lst) / len(lst)) if lst else 50

    asset_score = avg(cat_scores["asset"])
    time_score = avg(cat_scores["time"])
    body_score = avg(cat_scores["body"])
    emotion_score = avg(cat_scores["emotion"])
    network_score = avg(cat_scores["network"])
    system_score = avg(cat_scores["system"])
    overall = avg([asset_score, time_score, body_score, emotion_score, network_score, system_score])

    # health_index 테이블 업데이트 (Supabase 직접 연동)
    try:
        from app.supabase_client import get_supabase_admin
        sb = get_supabase_admin()

        # 기존 레코드 확인 후 upsert
        # ⚠️ 컬럼명은 health_index 테이블 실제 컬럼명과 일치해야 함
        sb.table("health_index").upsert({
            "vip_id": vip_id,
            "asset_stability": asset_score,       # asset → asset_stability
            "time_independence": time_score,      # time → time_independence
            "physical_condition": body_score,     # body → physical_condition
            "emotional_balance": emotion_score,   # emotion → emotional_balance
            "network_power": network_score,       # network → network_power
            "system_leverage": system_score,      # system → system_leverage
            "overall_score": overall,
        }, on_conflict="vip_id").execute()

    except Exception as e:
        # Supabase 연동 실패 시 로컬 DB에 저장 시도
        import logging
        logging.getLogger(__name__).warning(f"Supabase upsert failed, using local DB: {e}")
        try:
            existing = db.query(HealthIndex).filter(HealthIndex.vip_id == vip_id).first()
            if existing:
                existing.asset_stability = asset_score
                existing.time_independence = time_score
                existing.physical_condition = body_score
                existing.emotional_balance = emotion_score
                existing.network_power = network_score
                existing.system_leverage = system_score
                existing.overall_score = overall
            else:
                new_hi = HealthIndex(
                    id=str(uuid.uuid4()),
                    vip_id=vip_id,
                    asset_stability=asset_score,
                    time_independence=time_score,
                    physical_condition=body_score,
                    emotional_balance=emotion_score,
                    network_power=network_score,
                    system_leverage=system_score,
                    overall_score=overall,
                )
                db.add(new_hi)
            db.commit()
        except Exception as db_err:
            import logging
            logging.getLogger(__name__).error(f"Local DB save also failed: {db_err}")

    # 세션 정리
    _diagnosis_sessions.pop(vip_id, None)

    return {
        "diagnosis_id": vip_id,
        "scores": {
            "asset": asset_score, "time": time_score, "body": body_score,
            "emotion": emotion_score, "network": network_score, "system": system_score
        },
        "total_score": overall,
        "message": "진단이 완료되었습니다."
    }
