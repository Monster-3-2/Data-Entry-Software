import os
from datetime import datetime, timedelta
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, EmailStr
from jose import jwt
from db import supabase, supabase_admin
from models.auth_deps import get_current_user

router = APIRouter()

SECRET_KEY = os.environ.get("SECRET_KEY", "changeme-at-least-32-chars-long!!")
ALGORITHM  = "HS256"
TOKEN_EXP_HOURS = 12

class LoginRequest(BaseModel):
    email: EmailStr
    password: str

class CreateUserRequest(BaseModel):
    email: EmailStr
    password: str
    name: str
    role: str = "operator"


def make_token(user_id: str) -> str:
    exp = datetime.utcnow() + timedelta(hours=TOKEN_EXP_HOURS)
    return jwt.encode({"sub": user_id, "exp": exp}, SECRET_KEY, algorithm=ALGORITHM)


@router.post("/login")
def login(req: LoginRequest):
    # Authenticate via Supabase Auth
    try:
        res = supabase.auth.sign_in_with_password({"email": req.email, "password": req.password})
    except Exception as e:
        raise HTTPException(status_code=401, detail="Invalid email or password")

    if not res.user:
        raise HTTPException(status_code=401, detail="Invalid email or password")

    user_id = res.user.id

    # Fetch profile
    profile = supabase_admin.table("user_profiles").select("*").eq("id", user_id).single().execute()
    if not profile.data:
        raise HTTPException(status_code=403, detail="No profile found. Contact admin.")
    if not profile.data.get("is_active"):
        raise HTTPException(status_code=403, detail="Account is deactivated.")

    token = make_token(user_id)

    return {
        "access_token": token,
        "token_type": "bearer",
        "user": {
            "id": user_id,
            "name": profile.data["name"],
            "email": profile.data["email"],
            "role": profile.data["role"],
        }
    }


@router.post("/logout")
def logout(user=Depends(get_current_user)):
    # JWT is stateless; client clears token
    return {"message": "Logged out"}


@router.get("/me")
def me(user=Depends(get_current_user)):
    return user


@router.post("/users")
def create_user(req: CreateUserRequest, user=Depends(get_current_user)):
    """Admin only — create a new user"""
    if user["role"] != "admin":
        raise HTTPException(status_code=403, detail="Admin only")
    if req.role not in ("admin", "operator", "viewer"):
        raise HTTPException(status_code=400, detail="Invalid role")

    # Create in Supabase Auth
    try:
        auth_res = supabase_admin.auth.admin.create_user({
            "email": req.email,
            "password": req.password,
            "email_confirm": True,
        })
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

    new_id = auth_res.user.id

    # Create profile
    supabase_admin.table("user_profiles").insert({
        "id": new_id,
        "name": req.name,
        "email": req.email,
        "role": req.role,
    }).execute()

    return {"id": new_id, "name": req.name, "email": req.email, "role": req.role}
