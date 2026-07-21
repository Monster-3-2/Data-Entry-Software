import os
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv

load_dotenv()

from routes import auth, master, production, analytics

app = FastAPI(
    title="MAHLE Production API",
    description="Automobile thermal systems production management backend",
    version="1.0.0",
)

# ── CORS ────────────────────────────────────────────────────
FRONTEND_URL = os.environ.get("FRONTEND_URL", "https://data-entry-software.vercel.app")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        FRONTEND_URL,
        "https://data-entry-software.vercel.app",
        "http://127.0.0.1:5500",
        "http://localhost:5500",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── GZip compression (speeds up all JSON responses) ─────────
app.add_middleware(GZipMiddleware, minimum_size=500)

# ── Global exception handler — never let DB errors return 500
# with no body (which confuses the frontend into looping retries)
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    import traceback
    traceback.print_exc()
    origin = request.headers.get("origin", "*")
    return JSONResponse(
        status_code=503,
        content={"detail": f"Service temporarily unavailable: {type(exc).__name__}"},
        headers={
            "Access-Control-Allow-Origin":  origin,
            "Access-Control-Allow-Credentials": "true",
            "Access-Control-Allow-Methods": "*",
            "Access-Control-Allow-Headers": "*",
        }
    )

# ── Routers ─────────────────────────────────────────────────
app.include_router(auth.router,       prefix="/api/auth",       tags=["Auth"])
app.include_router(master.router,     prefix="/api/master",     tags=["Master"])
app.include_router(production.router, prefix="/api/production", tags=["Production"])
app.include_router(analytics.router,  prefix="/api/analytics",  tags=["Analytics"])

# ── Health / wake-up endpoint ────────────────────────────────
@app.get("/")
def health():
    return {"status": "ok", "service": "MAHLE Production API"}

@app.get("/api/health")
async def api_health(request: Request):
    """
    Dedicated health endpoint — always returns 200 with CORS headers when app is running.
    Used by frontend to poll until server is ready after cold start.
    This route is intentionally BEFORE any DB calls so it responds even if Supabase is slow.
    """
    origin = request.headers.get("origin", "*")
    from fastapi.responses import JSONResponse
    return JSONResponse(
        content={"status": "ok", "ready": True},
        headers={
            "Access-Control-Allow-Origin": origin,
            "Access-Control-Allow-Credentials": "true",
        }
    )

@app.options("/{rest_of_path:path}")
async def preflight_handler(rest_of_path: str, request: Request):
    """Handle CORS preflight for all routes explicitly."""
    origin = request.headers.get("origin", "*")
    return JSONResponse(
        content={},
        headers={
            "Access-Control-Allow-Origin":  origin,
            "Access-Control-Allow-Credentials": "true",
            "Access-Control-Allow-Methods": "GET, POST, PUT, DELETE, OPTIONS",
            "Access-Control-Allow-Headers": "Authorization, Content-Type",
            "Access-Control-Max-Age":       "86400",
        }
    )

# ── Cache headers middleware — tell browsers to cache GET responses
# master data (lines, shifts, etc.) can be cached for 60s in the browser
@app.middleware("http")
async def add_cache_headers(request: Request, call_next):
    try:
        response = await call_next(request)
    except Exception as exc:
        # Re-raise so global_exception_handler can catch it with CORS headers
        raise exc
    if request.method == "GET" and response.status_code == 200:
        path = request.url.path
        # Master data: cache 60s (changes rarely)
        if any(path.startswith(p) for p in ["/api/master/lines", "/api/master/shifts",
                                              "/api/master/reasons", "/api/master/models",
                                              "/api/master/shift-groups"]):
            response.headers["Cache-Control"] = "public, max-age=60, stale-while-revalidate=120"
        # Analytics: cache 90s
        elif path.startswith("/api/analytics"):
            response.headers["Cache-Control"] = "public, max-age=90, stale-while-revalidate=180"
        # Production entries: no cache (real-time)
        elif path.startswith("/api/production"):
            response.headers["Cache-Control"] = "no-cache"
    return response
