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

@app.get("/my-ip")
async def get_my_ip():
    """Railway 서버의 실제 outbound IP 확인용 (알리고 IP 등록에 사용)"""
    import httpx
    try:
        async with httpx.AsyncClient() as client:
            r = await client.get("https://api.ipify.org?format=json", timeout=5)
            return r.json()
    except Exception as e:
        return {"error": str(e)}


try:
    from app.database import engine, Base
    Base.metadata.create_all(bind=engine)
except Exception as e:
    import logging
    logging.getLogger(__name__).error(f"DB 연결 실패: {e}")

from app.api import survey, report, admin, agent, vip, community, quest, auth, payment, flow_deck, kakao
app.include_router(survey.router, prefix="/api/survey", tags=["survey"])
app.include_router(report.router, prefix="/api/report", tags=["report"])
app.include_router(admin.router, prefix="/api/admin", tags=["admin"])
app.include_router(agent.router, prefix="/api/agent", tags=["agent"])
app.include_router(vip.router, prefix="/api/vip", tags=["vip"])
app.include_router(community.router, prefix="/api/community", tags=["community"])
app.include_router(quest.router, prefix="/api/quests", tags=["quests"])
app.include_router(auth.router, prefix="/api/auth", tags=["auth"])
app.include_router(payment.router, prefix="/api/payment", tags=["payment"])
app.include_router(flow_deck.router, prefix="/api/flow-deck", tags=["flow-deck"])
app.include_router(kakao.router, prefix="/api/kakao", tags=["kakao"])
