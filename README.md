<<<<<<< HEAD
# MAHLE Production Management System

Automobile thermal systems production tracking platform.

## Stack
- **Frontend**: Vanilla HTML/CSS/JS → Vercel
- **Backend**: Python FastAPI → Render
- **Database**: Supabase (PostgreSQL)

## Folder Structure
```
mahle-production/
├── frontend/          # Static site → deploy to Vercel
│   ├── index.html     # Login page
│   ├── dashboard.html # Home dashboard
│   ├── master/        # Admin master data pages
│   ├── production/    # Production entry pages
│   ├── analytics/     # Charts & reports
│   └── assets/        # CSS, JS, images
├── backend/           # FastAPI → deploy to Render
│   ├── main.py
│   ├── db.py
│   ├── routes/
│   └── models/
└── supabase/
    └── schema.sql     # Run this first in Supabase SQL editor
```

## Setup

### 1. Supabase
- Create project at supabase.com
- Run `supabase/schema.sql` in the SQL editor
- Copy your Project URL and anon key

### 2. Backend (Render)
- Connect GitHub repo → New Web Service
- Root dir: `backend/`
- Build: `pip install -r requirements.txt`
- Start: `uvicorn main:app --host 0.0.0.0 --port 10000`
- Add env vars: `SUPABASE_URL`, `SUPABASE_KEY`, `SECRET_KEY`

### 3. Frontend (Vercel)
- Connect GitHub repo → New Project
- Root dir: `frontend/`
- Update `assets/js/config.js` with your Render backend URL

## User Roles
| Role | Access |
|------|--------|
| Admin | Full control — master data, production, analytics, users |
| Operator | Production entry only |
| Viewer | Analytics & graphs only (read-only) |
=======
# Data-Entry-Software
helps manage data and analyse it
>>>>>>> dea1723ecac74ae39931e4be73151102f2eb6e0b
