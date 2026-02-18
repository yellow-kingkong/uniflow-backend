from pydantic_settings import BaseSettings
from functools import lru_cache
from typing import Optional

class Settings(BaseSettings):
    # Database
    database_url: str
    
    # Redis
    redis_url: str
    
    # OpenAI
    openai_api_key: str
    
    # Anthropic (Optional)
    anthropic_api_key: Optional[str] = None
    
    # Kakao
    kakao_api_key: str
    kakao_sender_key: str
    
    # AWS SES (Optional)
    aws_access_key_id: Optional[str] = None
    aws_secret_access_key: Optional[str] = None
    aws_region: str = "ap-northeast-2"
    
    # Application
    app_env: str = "development"
    secret_key: str
    frontend_url: str = "https://uniflow.ai.kr"
    next_public_base_url: str = "https://uniflow.ai.kr"
    next_public_site_url: str = "https://uniflow.ai.kr"
    
    # Supabase (Optional)
    supabase_url: Optional[str] = None
    supabase_service_role_key: Optional[str] = None
    
    # SMTP (Gmail)
    smtp_host: str = "smtp.gmail.com"
    smtp_port: int = 587
    smtp_user: Optional[str] = "uniflow.ss@gmail.com"
    smtp_password: Optional[str] = None # To be set in .env
    sender_email: str = "uniflow.ss@gmail.com"
    
    class Config:
        env_file = ".env"
        case_sensitive = False
        extra = "ignore"


@lru_cache()
def get_settings() -> Settings:
    return Settings()
