from pydantic_settings import BaseSettings
from functools import lru_cache
from typing import Optional

class Settings(BaseSettings):
    database_url: str
    redis_url: Optional[str] = None
    openai_api_key: str
    anthropic_api_key: Optional[str] = None
    kakao_api_key: Optional[str] = None
    kakao_sender_key: Optional[str] = None
    aws_access_key_id: Optional[str] = None
    aws_secret_access_key: Optional[str] = None
    aws_region: str = "ap-northeast-2"
    app_env: str = "development"
    secret_key: str = "default-secret-key"
    frontend_url: str = "https://uniflow.ai.kr"
    next_public_base_url: str = "https://uniflow.ai.kr"
    next_public_site_url: str = "https://uniflow.ai.kr"
    supabase_url: Optional[str] = None
    supabase_service_role_key: Optional[str] = None
    smtp_host: str = "smtp.gmail.com"
    smtp_port: int = 587
    smtp_user: Optional[str] = None
    smtp_password: Optional[str] = None
    sender_email: str = "uniflow.ss@gmail.com"

    class Config:
        env_file = ".env"
        case_sensitive = False
        extra = "ignore"

@lru_cache()
def get_settings() -> Settings:
    return Settings()
