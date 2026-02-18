"""
설문 API 엔드포인트
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.database import get_db
from app.schemas import SurveySubmitRequest
from app.models import Survey, User

router = APIRouter()


@router.post("/submit")
async def submit_survey(
    survey_data: SurveySubmitRequest,
    db: Session = Depends(get_db)
):
    """설문 응답 제출"""
    
    # 1. 사용자 생성 또는 조회
    user = db.query(User).filter(User.phone == survey_data.phone).first()
    if not user:
        user = User(
            name=survey_data.name,
            phone=survey_data.phone,
            email=survey_data.email
        )
        db.add(user)
        db.commit()
        db.refresh(user)
    
    # 2. 설문 응답 저장
    survey = Survey(
        name=survey_data.name,
        phone=survey_data.phone,
        email=survey_data.email,
        business_type=survey_data.business_type,
        industry=survey_data.industry,
        years_in_business=survey_data.years_in_business,
        revenue_range=survey_data.revenue_range,
        team_size=survey_data.team_size,
        responses=survey_data.responses
    )
    
    db.add(survey)
    db.commit()
    db.refresh(survey)
    
    return {
        "success": True,
        "survey_id": survey.id,
        "message": "설문이 성공적으로 제출되었습니다."
    }


@router.get("/{survey_id}")
async def get_survey(survey_id: int, db: Session = Depends(get_db)):
    """설문 조회"""
    survey = db.query(Survey).filter(Survey.id == survey_id).first()
    if not survey:
        raise HTTPException(status_code=404, detail="설문을 찾을 수 없습니다.")
    
    return survey
