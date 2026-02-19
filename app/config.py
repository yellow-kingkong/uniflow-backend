from pydantic_settings import BaseSettings
from functools import lru_cache
from typing import Optional

class Settings(BaseSettings):
    # Database (필수)
    database_url: str
    
    # Redis (Optional)
    redis_url: Optional[str] = None
    
    # OpenAI (필수 - 진단 AI에 필요)
    openai_api_key: str
    
    # Anthropic (Optional)
    anthropic_api_key: Optional[str] = None
    
    # Kakao Alimtalk via SOLAPI (Optional)
    # SOLAPI(구 SMS아이디어)를 통한 카카오 알림톡 발송
    kakao_api_key: Optional[str] = None        # SOLAPI API Key
    kakao_api_secret: Optional[str] = None     # SOLAPI API Secret
    kakao_sender_key: Optional[str] = None     # 카카오 채널 pfId
    kakao_sender_number: Optional[str] = None  # 발신번호
    
    # AWS SES (Optional)
    aws_access_key_id: Optional[str] = None
    aws_secret_access_key: Optional[str] = None
    aws_region: str = "ap-northeast-2"
    
    # Application
    app_env: str = "development"
    secret_key: str = "default-secret-key-change-in-production"
    frontend_url: str = "https://uniflow.ai.kr"
    next_public_base_url: str = "https://uniflow.ai.kr"
    next_public_site_url: str = "https://uniflow.ai.kr"
    
    # Supabase (Optional)
    supabase_url: Optional[str] = None
    supabase_service_role_key: Optional[str] = None
    
    # 토스페이먼츠 (Optional - 없으면 결제 기능 비활성화)
    # 테스트 키: test_sk_... / 프로덕션 키: live_sk_...
    tosspayments_secret_key: Optional[str] = None
    tosspayments_client_key: Optional[str] = None  # 프론트엔드에서 사용
    
    # SMTP (Optional)
    smtp_host: str = "smtp.gmail.com"
    smtp_port: int = 587
    smtp_user: Optional[str] = "uniflow.ss@gmail.com"
    smtp_password: Optional[str] = None
    sender_email: str = "uniflow.ss@gmail.com"
    
    class Config:
        env_file = ".env"
        case_sensitive = False
        extra = "ignore"


@lru_cache()
def get_settings() -> Settings:
    return Settings()
