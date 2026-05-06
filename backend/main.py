import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv

load_dotenv()

from routes import auth, master, production, analytics

app = FastAPI(
    title="MAHLE Production API",
    description="Automobile thermal systems production management backend",
    version="1.0.0",
)

# CORS — allow frontend origin
FRONTEND_URL = os.environ.get("FRONTEND_URL", "https://data-entry-software.vercel.app/")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[FRONTEND_URL, "https://data-entry-software.vercel.app/", "http://127.0.0.1:5500"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount routers
app.include_router(auth.router,       prefix="/api/auth",       tags=["Auth"])
app.include_router(master.router,     prefix="/api/master",     tags=["Master"])
app.include_router(production.router, prefix="/api/production", tags=["Production"])
app.include_router(analytics.router,  prefix="/api/analytics",  tags=["Analytics"])

@app.get("/")
def health():
    return {"status": "ok", "service": "MAHLE Production API"}
