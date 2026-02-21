from supabase import create_client, Client
from app.config import get_settings

settings = get_settings()

supabase_url = settings.supabase_url
supabase_key = settings.supabase_service_role_key

def get_supabase_admin() -> Client:
    """서비스 롤 키로 Supabase 클라이언트를 반환합니다."""
    if not supabase_url or not supabase_key:
        raise ValueError("Supabase credentials not configured in .env")
    return create_client(supabase_url, supabase_key)

# flow_deck.py 등에서 get_supabase() 이름으로 import하는 경우를 위한 alias
# (함수명 불일치로 인한 ImportError 방지)
get_supabase = get_supabase_admin
