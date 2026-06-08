import os
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import jwt, JWTError
from db import supabase_admin

SECRET_KEY = os.environ.get("SECRET_KEY", "changeme-at-least-32-chars-long!!")
ALGORITHM = "HS256"

bearer_scheme = HTTPBearer()

def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme)):
    token = credentials.credentials
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id: str = payload.get("sub")
        if not user_id:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")
    except JWTError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired token")

    # Fetch profile — wrap in try/except so DB errors return 401 not 500
    try:
        res = supabase_admin.table("user_profiles").select("*").eq("id", user_id).single().execute()
        if not res.data:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")
        return res.data
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=f"Database unavailable: {str(e)}")

def require_admin(user=Depends(get_current_user)):
    if user["role"] != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin access required")
    return user

def require_operator_or_admin(user=Depends(get_current_user)):
    # product_lead = renamed operator (can enter + edit)
    # operator = new restricted role (entry only, cannot edit target/master)
    if user["role"] not in ("admin", "product_lead", "operator"):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access required")
    return user

def require_product_lead_or_admin(user=Depends(get_current_user)):
    if user["role"] not in ("admin", "product_lead"):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Product Lead or Admin required")
    return user
