"""
앱 전역 설정 모듈
- 환경변수를 읽어 Settings 객체로 관리
- get_settings()로 싱글톤 인스턴스 제공
"""
from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    # ─── 데이터베이스 ───────────────────────────────
    database_url: str = ""

    # ─── Supabase ────────────────────────────────────
    supabase_url: str = ""
    supabase_service_role_key: str = ""

    # ─── 앱 보안 ─────────────────────────────────────
    secret_key: str = "change-me-in-production"

    # ─── AI 서비스 ────────────────────────────────────
    openai_api_key: str = ""
    anthropic_api_key: str = ""

    # ─── 알리고 카카오 알림톡 ──────────────────────────
    kakao_api_key: str = ""      # 알리고 API Key (= ALIGO_API_KEY)
    kakao_api_secret: str = ""   # 알리고 로그인 ID (= ALIGO_USER_ID)
    kakao_sender_key: str = ""   # 발신프로필키 Senderkey (= KAKAO_CHANNEL_ID)
    kakao_sender_number: str = "" # 발신번호 (= ALIGO_SENDER_PHONE)
    # Railway 내부 호출 인증용 시크릿
    internal_secret: str = "uniflow-internal-2026"

    # ─── 토스페이먼츠 ─────────────────────────────────
    tosspayments_secret_key: str = ""
    tosspayments_client_key: str = ""

    # ─── 이메일(SMTP) ─────────────────────────────────
    smtp_password: str = ""

    # ─── 앱 URL ──────────────────────────────────────
    frontend_url: str = "https://uniflow.ai.kr"
    next_public_base_url: str = "https://uniflow.ai.kr"
    next_public_site_url: str = "https://uniflow.ai.kr"

    class Config:
        env_file = ".env"
        extra = "ignore"  # .env에 정의되지 않은 변수 무시


@lru_cache()
def get_settings() -> Settings:
    """설정 싱글톤 반환 (한 번만 로드 후 캐싱)"""
    return Settings()
