import os
import httpx
from supabase import create_client, Client
from dotenv import load_dotenv

load_dotenv()

SUPABASE_URL: str = os.environ["SUPABASE_URL"]
SUPABASE_KEY: str = os.environ["SUPABASE_KEY"]
SUPABASE_SERVICE_KEY: str = os.environ.get("SUPABASE_SERVICE_KEY", SUPABASE_KEY)

def _make_client(url: str, key: str) -> Client:
    client = create_client(url, key)
    # Replace the postgrest httpx session with one that forces HTTP/1.1.
    # The default HTTP/2 connection shares streams over one socket; under load
    # on Render's free tier this causes ReadError [Errno 11] (EAGAIN).
    # HTTP/1.1 opens separate connections and avoids this entirely.
    try:
        http1_session = httpx.Client(http2=False, timeout=30.0)
        client.postgrest.session = http1_session
    except Exception:
        pass  # If patching fails, continue with default — better than crashing at startup
    return client

# Anon client — respects RLS
supabase: Client = _make_client(SUPABASE_URL, SUPABASE_KEY)

# Service client — bypasses RLS (use only in admin operations)
supabase_admin: Client = _make_client(SUPABASE_URL, SUPABASE_SERVICE_KEY)
