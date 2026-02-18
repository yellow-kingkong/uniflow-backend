from supabase import create_client, Client
from app.config import get_settings

settings = get_settings()

supabase_url = settings.supabase_url
supabase_key = settings.supabase_service_role_key

def get_supabase_admin() -> Client:
    if not supabase_url or not supabase_key:
        raise ValueError("Supabase credentials not configured in .env")
    return create_client(supabase_url, supabase_key)
