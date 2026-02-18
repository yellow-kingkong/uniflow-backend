from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.config import get_settings
from app.database import engine, Base

# 데이터베이스 테이블 생성
Base.metadata.create_all(bind=engine)

settings = get_settings()

app = FastAPI(
    title="Uniflow AI Report System",
    description="비즈니스 진단 AI 리포트 생성 시스템",
    version="1.0.0"
)

# CORS 설정
app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.frontend_url],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 백그라운드 작업 (구독/체험 만료 체크)
# from app.services.subscription import check_subscriptions

# @app.on_event("startup")
# async def startup_event():
#     # 1시간마다 구독 상태 체크 (백그라운드 루프)
#     async def subscription_worker():
#         while True:
#             try:
#                 # check_subscriptions()
#                 pass
#             except Exception as e:
#                 import logging
#                 logging.getLogger(__name__).error(f"Subscription worker error: {str(e)}")
#             await asyncio.sleep(3600 * 12) # 12시간마다 실행
#             
#     asyncio.create_task(subscription_worker())


@app.get("/")
async def root():
    return {
        "message": "Uniflow AI Report System",
        "status": "running",
        "version": "1.0.0"
    }


@app.get("/health")
async def health_check():
    return {"status": "healthy"}


# API 라우터 등록
from app.api import survey, report, admin, agent, vip, community, quest, auth, payment

app.include_router(survey.router, prefix="/api/survey", tags=["survey"])
app.include_router(report.router, prefix="/api/report", tags=["report"])
app.include_router(admin.router, prefix="/api/admin", tags=["admin"])
app.include_router(agent.router, prefix="/api/agent", tags=["agent"])
app.include_router(vip.router, prefix="/api/vip", tags=["vip"])
app.include_router(community.router, prefix="/api/community", tags=["community"])
app.include_router(quest.router, prefix="/api/quests", tags=["quests"])
app.include_router(auth.router, prefix="/api/auth", tags=["auth"])
app.include_router(payment.router, prefix="/api/payment", tags=["payment"])
