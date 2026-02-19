from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.config import get_settings

settings = get_settings()

app = FastAPI(title="Uniflow AI Report System", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://uniflow.ai.kr",
        "https://uniflow-ss.vercel.app",
        "http://localhost:5173",
        "http://localhost:3000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
async def root():
    return {"message": "Uniflow AI Report System", "status": "running"}

@app.get("/health")
async def health_check():
    return {"status": "healthy"}

try:
    from app.database import engine, Base
    Base.metadata.create_all(bind=engine)
except Exception as e:
    import logging
    logging.getLogger(__name__).error(f"DB 연결 실패: {e}")

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
