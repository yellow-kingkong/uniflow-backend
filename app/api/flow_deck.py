"""
FLOW Deck API 라우터
- POST /api/flow-deck/generate  : 인터뷰 데이터 → PPTX 생성 → Supabase Storage 업로드 → URL 반환
- GET  /api/flow-deck/status/{session_id} : 세션 처리 상태 조회
"""
import uuid
import logging
from io import BytesIO
from fastapi import APIRouter, HTTPException, BackgroundTasks
from pydantic import BaseModel
from typing import Optional

from app.services.pptx_generator import generate_pptx
from app.supabase_client import get_supabase

logger = logging.getLogger(__name__)
router = APIRouter()


# ─── 요청 스키마 ──────────────────────────────────────────────────────────────
class GenerateRequest(BaseModel):
    session_id: str                             # flow_deck_sessions.id
    agent_id: str                               # 에이전트 UUID
    interview_data: dict                        # 인터뷰에서 수집된 데이터
    ai_summary: Optional[str] = None           # AI 요약 (있으면 기대효과 슬라이드에 반영)
    output_format: list[str] = ["pptx"]        # ["pptx"] or ["pptx", "pdf"]


# ─── 비동기 백그라운드 생성 작업 ──────────────────────────────────────────────
async def _generate_and_upload(
    session_id: str,
    agent_id: str,
    interview_data: dict,
    ai_summary: Optional[str],
    output_format: list[str],
):
    """
    PPTX를 생성하고 Supabase Storage에 업로드한 뒤
    flow_deck_sessions 테이블을 업데이트합니다.
    """
    supabase = get_supabase()
    try:
        # 1. 상태 → processing
        supabase.table("flow_deck_sessions").update(
            {"status": "processing"}
        ).eq("id", session_id).execute()

        # 2. PPTX 생성
        logger.info(f"[FlowDeck] PPTX 생성 시작: session={session_id}")
        pptx_bytes = generate_pptx(interview_data, ai_summary)

        # 3. Supabase Storage 업로드 경로
        title = interview_data.get("proposalTitle") or interview_data.get("title") or "proposal"
        safe_title = "".join(c if c.isalnum() or c in "-_" else "_" for c in title)[:40]
        file_key = f"flow_deck/{agent_id}/{session_id}/{safe_title}.pptx"

        # 4. 업로드
        res = supabase.storage.from_("flow-deck-files").upload(
            path=file_key,
            file=pptx_bytes,
            file_options={"content-type": "application/vnd.openxmlformats-officedocument.presentationml.presentation"},
        )
        if hasattr(res, "error") and res.error:
            raise RuntimeError(f"Storage 업로드 실패: {res.error}")

        # 5. 공개 URL 조회
        url_res = supabase.storage.from_("flow-deck-files").get_public_url(file_key)
        pptx_url = url_res  # 문자열 반환

        # 6. 세션 업데이트
        supabase.table("flow_deck_sessions").update({
            "status": "completed",
            "pptx_url": pptx_url,
        }).eq("id", session_id).execute()

        logger.info(f"[FlowDeck] 완료: session={session_id} url={pptx_url}")

    except Exception as e:
        logger.error(f"[FlowDeck] 생성 실패: session={session_id} err={e}")
        supabase.table("flow_deck_sessions").update({
            "status": "failed",
        }).eq("id", session_id).execute()


# ─── 엔드포인트: 생성 요청 ────────────────────────────────────────────────────
@router.post("/generate")
async def generate_flow_deck(
    req: GenerateRequest,
    background_tasks: BackgroundTasks,
):
    """
    PPTX 생성을 백그라운드로 처리합니다.
    즉시 202 응답을 반환하고, 프론트엔드는 /status/{session_id}로 폴링합니다.
    """
    # 간단한 보안: interview_data에 agent_id가 일치하는지 확인
    if not req.session_id or not req.agent_id:
        raise HTTPException(status_code=400, detail="session_id와 agent_id가 필요합니다.")

    # 백그라운드 작업 등록
    background_tasks.add_task(
        _generate_and_upload,
        session_id=req.session_id,
        agent_id=req.agent_id,
        interview_data=req.interview_data,
        ai_summary=req.ai_summary,
        output_format=req.output_format,
    )

    return {
        "ok": True,
        "message": "PPTX 생성이 시작되었습니다. 잠시 후 완료됩니다.",
        "session_id": req.session_id,
        "status": "processing",
    }


# ─── 엔드포인트: 상태 조회 ────────────────────────────────────────────────────
@router.get("/status/{session_id}")
async def get_session_status(session_id: str):
    """세션 처리 상태와 완료 시 다운로드 URL을 반환합니다."""
    supabase = get_supabase()
    try:
        res = supabase.table("flow_deck_sessions") \
            .select("id, status, pptx_url, title") \
            .eq("id", session_id) \
            .maybe_single() \
            .execute()

        if not res.data:
            raise HTTPException(status_code=404, detail="세션을 찾을 수 없습니다.")

        data = res.data
        return {
            "ok": True,
            "session_id": session_id,
            "status": data.get("status"),
            "pptx_url": data.get("pptx_url"),
            "title": data.get("title"),
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[FlowDeck] 상태 조회 실패: {e}")
        raise HTTPException(status_code=500, detail=str(e))
