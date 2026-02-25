"""
FLOW Deck API 라우터 v3
- POST /api/flow-deck/generate  : 인터뷰 데이터 → PDF 생성 → Supabase Storage 업로드 → URL 반환
- GET  /api/flow-deck/status/{session_id} : 세션 처리 상태 조회

수정 사항 (v3):
- async 컨텍스트에서 동기 generate_pdf()를 run_in_executor()로 안전 실행
  (이전: nest_asyncio 충돌로 Railway 500 에러 발생)
- Storage upsert 옵션: 문자열 "true" → bool True
- pptx_url 컬럼 유지 (FlowDeckSession.tsx 하위 호환)
"""
import logging
import asyncio
from functools import partial
from fastapi import APIRouter, HTTPException, BackgroundTasks
from pydantic import BaseModel
from typing import Optional

logger = logging.getLogger(__name__)
router = APIRouter()


# ─── 요청 스키마 ─────────────────────────────────────────────────────────────
class GenerateRequest(BaseModel):
    session_id: str
    agent_id: str
    interview_data: dict
    ai_summary: Optional[str] = None
    output_format: list[str] = ["pdf"]


# ─── 비동기 백그라운드 생성 ──────────────────────────────────────────────────
async def _generate_and_upload(
    session_id: str,
    agent_id: str,
    interview_data: dict,
    ai_summary: Optional[str],
):
    """
    PDF를 생성하고 Supabase Storage에 업로드한 뒤
    flow_deck_sessions 테이블을 업데이트합니다.

    ⚠️ 핵심 설계:
    - generate_pdf()는 pyppeteer를 사용하는 동기 함수
    - FastAPI 백그라운드 태스크는 async 컨텍스트에서 실행
    - 해결: run_in_executor()로 별도 스레드에서 실행 → asyncio 이벤트 루프 충돌 없음
    """
    try:
        from app.supabase_client import get_supabase
        supabase = get_supabase()
    except Exception as e:
        logger.error(f"[FlowDeck] Supabase 초기화 실패: {e}")
        return

    try:
        # 1. 상태 → processing
        supabase.table("flow_deck_sessions").update(
            {"status": "processing"}
        ).eq("id", session_id).execute()

        # 2. PDF 생성 (스레드 풀에서 실행 — asyncio 이벤트 루프 충돌 방지)
        logger.info(f"[FlowDeck] PDF 생성 시작: session={session_id}")
        from app.services.slide_generator import generate_pdf

        loop = asyncio.get_event_loop()
        pdf_bytes = await loop.run_in_executor(
            None,  # 기본 ThreadPoolExecutor 사용
            partial(generate_pdf, interview_data, ai_summary)
        )
        logger.info(f"[FlowDeck] PDF 생성 완료: {len(pdf_bytes)} bytes")

        # 3. 파일 경로 구성
        title = interview_data.get("proposalTitle") or interview_data.get("title") or "proposal"
        safe_title = "".join(c if c.isalnum() or c in "-_" else "_" for c in title)[:40]
        file_key = f"flow_deck/{agent_id}/{session_id}/{safe_title}.pdf"

        # 4. Supabase Storage 업로드
        res = supabase.storage.from_("flow-deck-files").upload(
            path=file_key,
            file=pdf_bytes,
            file_options={
                "content-type": "application/pdf",
                "upsert": True,  # bool True 사용 (문자열 "true"는 일부 버전에서 오류)
            },
        )
        # supabase-py 버전별 에러 체크
        if hasattr(res, "error") and res.error:
            raise RuntimeError(f"Storage 업로드 실패: {res.error}")
        elif isinstance(res, dict) and res.get("error"):
            raise RuntimeError(f"Storage 업로드 실패: {res.get('error')}")

        # 5. 공개 URL
        pdf_url = supabase.storage.from_("flow-deck-files").get_public_url(file_key)
        logger.info(f"[FlowDeck] 업로드 완료: {pdf_url}")

        # 6. DB 업데이트
        # pptx_url 컬럼에 저장 → FlowDeckSession.tsx가 pptx_url로 폴링하기 때문
        supabase.table("flow_deck_sessions").update({
            "status": "completed",
            "pptx_url": pdf_url,
        }).eq("id", session_id).execute()

        logger.info(f"[FlowDeck] 완료: session={session_id}")

    except Exception as e:
        logger.error(f"[FlowDeck] 생성 실패: session={session_id} err={e}", exc_info=True)
        try:
            supabase.table("flow_deck_sessions").update({
                "status": "failed",
            }).eq("id", session_id).execute()
        except Exception as e2:
            logger.error(f"[FlowDeck] 상태 업데이트 실패: {e2}")


# ─── 엔드포인트: 생성 요청 ────────────────────────────────────────────────────
@router.post("/generate")
async def generate_flow_deck(
    req: GenerateRequest,
    background_tasks: BackgroundTasks,
):
    """
    PDF 생성을 백그라운드로 처리합니다.
    즉시 200 응답을 반환하고, 프론트엔드는 /status/{session_id}로 폴링합니다.
    """
    if not req.session_id or not req.agent_id:
        raise HTTPException(status_code=400, detail="session_id와 agent_id가 필요합니다.")

    background_tasks.add_task(
        _generate_and_upload,
        session_id=req.session_id,
        agent_id=req.agent_id,
        interview_data=req.interview_data,
        ai_summary=req.ai_summary,
    )

    return {
        "ok": True,
        "message": "PDF 생성이 시작되었습니다. 잠시 후 완료됩니다.",
        "session_id": req.session_id,
        "status": "processing",
    }


# ─── 엔드포인트: 상태 조회 ────────────────────────────────────────────────────
@router.get("/status/{session_id}")
async def get_session_status(session_id: str):
    """세션 처리 상태와 완료 시 다운로드 URL을 반환합니다."""
    try:
        from app.supabase_client import get_supabase
        supabase = get_supabase()
    except Exception as e:
        logger.error(f"[FlowDeck] Supabase 초기화 실패: {e}")
        raise HTTPException(status_code=500, detail="DB 연결 실패")

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
            "pptx_url": data.get("pptx_url"),   # 프론트 호환
            "title": data.get("title"),
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[FlowDeck] 상태 조회 실패: {e}")
        raise HTTPException(status_code=500, detail=str(e))
