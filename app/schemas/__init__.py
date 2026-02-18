from pydantic import BaseModel, Field
from typing import Dict, Any, Optional


class SurveySubmitRequest(BaseModel):
    """설문 제출 요청"""
    # 사용자 정보
    name: str = Field(..., description="이름")
    phone: str = Field(..., description="전화번호")
    email: Optional[str] = Field(None, description="이메일")
    
    # 비즈니스 정보
    business_type: str = Field(..., description="대표/프리랜서/자영업")
    industry: str = Field(..., description="업종")
    years_in_business: int = Field(..., description="업력 (년)")
    revenue_range: str = Field(..., description="매출 구간")
    team_size: int = Field(..., description="팀 규모")
    
    # 설문 응답
    responses: Dict[str, Any] = Field(..., description="설문 응답 데이터")


class ReportGenerateRequest(BaseModel):
    """리포트 생성 요청"""
    survey_id: int = Field(..., description="설문 ID")


class ReportResponse(BaseModel):
    """리포트 응답"""
    report_id: int
    survey_id: int
    persona_type: str
    html_url: Optional[str] = None
    pdf_url: Optional[str] = None
    created_at: str
