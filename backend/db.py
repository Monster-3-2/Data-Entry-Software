import os
import time
from supabase import create_client, Client
from dotenv import load_dotenv

load_dotenv()

SUPABASE_URL: str        = os.environ["SUPABASE_URL"]
SUPABASE_KEY: str        = os.environ["SUPABASE_KEY"]
SUPABASE_SERVICE_KEY: str = os.environ.get("SUPABASE_SERVICE_KEY", SUPABASE_KEY)

supabase: Client       = create_client(SUPABASE_URL, SUPABASE_KEY)
supabase_admin: Client = create_client(SUPABASE_URL, SUPABASE_SERVICE_KEY)


def _reconnect():
    """Recreate Supabase clients to get fresh HTTP/2 connections after a drop."""
    global supabase, supabase_admin
    try:
        supabase       = create_client(SUPABASE_URL, SUPABASE_KEY)
        supabase_admin = create_client(SUPABASE_URL, SUPABASE_SERVICE_KEY)
    except Exception:
        pass
