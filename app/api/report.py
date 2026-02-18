"""
리포트 API 엔드포인트
"""
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from sqlalchemy.orm import Session
from app.database import get_db
from app.schemas import ReportGenerateRequest, ReportResponse
from app.models import Survey, Report
from app.agents.master_agent import MasterDiagnosticAgent
from app.services.report_generator import ReportGenerator
from app.services.kakao_sender import KakaoSender

router = APIRouter()


@router.post("/generate")
async def generate_report(
    request: ReportGenerateRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db)
):
    """AI 리포트 생성"""
    
    # 1. 설문 조회
    survey = db.query(Survey).filter(Survey.id == request.survey_id).first()
    if not survey:
        raise HTTPException(status_code=404, detail="설문을 찾을 수 없습니다.")
    
    # 2. 설문 데이터 준비
    survey_data = {
        "name": survey.name,
        "phone": survey.phone,
        "email": survey.email,
        "business_type": survey.business_type,
        "industry": survey.industry,
        "years_in_business": survey.years_in_business,
        "revenue_range": survey.revenue_range,
        "team_size": survey.team_size,
        "responses": survey.responses
    }
    
    # 3. AI 분석 실행
    master_agent = MasterDiagnosticAgent()
    analysis_result = master_agent.analyze(survey_data)
    
    # 4. 리포트 DB 저장
    report = Report(
        survey_id=survey.id,
        user_id=survey.id,  # 임시로 survey.id 사용
        persona_type=analysis_result["persona"]["persona_type"],
        bottlenecks=analysis_result["bottlenecks"],
        insights=analysis_result.get("insights", {}),
        recommendations=analysis_result.get("recommendations", {}),
        narrative_text=str(analysis_result["narrative"]),
        monthly_time_loss=analysis_result["bottlenecks"]["total_monthly_loss"]["time"],
        monthly_cost_loss=analysis_result["bottlenecks"]["total_monthly_loss"]["cost"],
        growth_delay_months=analysis_result["bottlenecks"]["growth_delay_months"],
        urgency_score=analysis_result["bottlenecks"]["overall_urgency"]
    )
    
    db.add(report)
    db.commit()
    db.refresh(report)
    
    # 5. HTML/PDF 리포트 생성 (백그라운드)
    background_tasks.add_task(
        generate_report_files,
        report_id=report.id,
        analysis_result=analysis_result,
        db=db
    )
    
    # 6. 카카오톡 발송 (백그라운드)
    background_tasks.add_task(
        send_kakao_notification,
        report_id=report.id,
        phone=survey.phone,
        name=survey.name,
        db=db
    )
    
    return {
        "success": True,
        "report_id": report.id,
        "persona_type": report.persona_type,
        "message": "리포트가 생성 중입니다. 곧 카카오톡으로 전송됩니다."
    }


@router.get("/{report_id}")
async def get_report(report_id: int, db: Session = Depends(get_db)):
    """리포트 조회"""
    report = db.query(Report).filter(Report.id == report_id).first()
    if not report:
        raise HTTPException(status_code=404, detail="리포트를 찾을 수 없습니다.")
    
    return ReportResponse(
        report_id=report.id,
        survey_id=report.survey_id,
        persona_type=report.persona_type,
        html_url=report.html_url,
        pdf_url=report.pdf_url,
        created_at=str(report.created_at)
    )


async def generate_report_files(report_id: int, analysis_result: dict, db: Session):
    """리포트 HTML/PDF 파일 생성 (백그라운드 작업)"""
    generator = ReportGenerator(analysis_result)
    
    # HTML 생성
    html_content = generator.generate_html()
    html_url = f"/reports/{report_id}.html"
    
    # PDF 생성
    pdf_content = generator.export_pdf()
    pdf_url = f"/reports/{report_id}.pdf"
    
    # DB 업데이트
    report = db.query(Report).filter(Report.id == report_id).first()
    if report:
        report.html_url = html_url
        report.pdf_url = pdf_url
        db.commit()


async def send_kakao_notification(report_id: int, phone: str, name: str, db: Session):
    """카카오톡 알림 발송 (백그라운드 작업)"""
    sender = KakaoSender()
    
    report_url = f"https://uniflow.ai.kr/report/{report_id}"
    
    success = sender.send_report(
        phone_number=phone,
        report_url=report_url,
        user_data={"name": name}
    )
    
    if success:
        report = db.query(Report).filter(Report.id == report_id).first()
        if report:
            report.kakao_sent = 1
            from datetime import datetime
            report.kakao_sent_at = datetime.now()
            db.commit()
