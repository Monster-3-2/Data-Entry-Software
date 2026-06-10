import os
from supabase import create_client, Client
from dotenv import load_dotenv
 
load_dotenv()
 
SUPABASE_URL: str = os.environ["SUPABASE_URL"]
SUPABASE_KEY: str = os.environ["SUPABASE_KEY"]
SUPABASE_SERVICE_KEY: str = os.environ.get("SUPABASE_SERVICE_KEY", SUPABASE_KEY)
 
# Anon client — respects RLS
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
 
# Service client — bypasses RLS (use only in admin operations)
supabase_admin: Client = create_client(SUPABASE_URL, SUPABASE_SERVICE_KEY)
