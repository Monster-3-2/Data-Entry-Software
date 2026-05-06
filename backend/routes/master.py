from fastapi import APIRouter, HTTPException, Depends, Query
from pydantic import BaseModel
from typing import Optional
from db import supabase_admin
from models.auth_deps import get_current_user, require_admin

router = APIRouter()

# ============================================================
# LINES
# ============================================================
class LineBody(BaseModel):
    name: Optional[str] = None
    is_active: Optional[bool] = None

@router.get("/lines")
def get_lines(user=Depends(get_current_user)):
    res = supabase_admin.table("lines").select("*").order("name").execute()
    return res.data

@router.post("/lines")
def create_line(body: LineBody, user=Depends(require_admin)):
    if not body.name:
        raise HTTPException(status_code=400, detail="Name is required")
    res = supabase_admin.table("lines").insert({"name": body.name}).execute()
    return res.data[0]

@router.put("/lines/{line_id}")
def update_line(line_id: str, body: LineBody, user=Depends(require_admin)):
    data = {k: v for k, v in body.dict().items() if v is not None}
    res = supabase_admin.table("lines").update(data).eq("id", line_id).execute()
    return res.data[0]

@router.delete("/lines/{line_id}")
def delete_line(line_id: str, user=Depends(require_admin)):
    supabase_admin.table("lines").delete().eq("id", line_id).execute()
    return {"deleted": True}

# ============================================================
# MODELS
# ============================================================
class ModelBody(BaseModel):
    line_id: Optional[str] = None
    name: Optional[str] = None
    is_active: Optional[bool] = None

@router.get("/models")
def get_models(line_id: Optional[str] = None, user=Depends(get_current_user)):
    q = supabase_admin.table("models").select("*").order("name")
    if line_id:
        q = q.eq("line_id", line_id)
    return q.execute().data

@router.post("/models")
def create_model(body: ModelBody, user=Depends(require_admin)):
    if not body.line_id or not body.name:
        raise HTTPException(status_code=400, detail="line_id and name required")
    res = supabase_admin.table("models").insert({"line_id": body.line_id, "name": body.name}).execute()
    return res.data[0]

@router.put("/models/{model_id}")
def update_model(model_id: str, body: ModelBody, user=Depends(require_admin)):
    data = {k: v for k, v in body.dict().items() if v is not None}
    res = supabase_admin.table("models").update(data).eq("id", model_id).execute()
    return res.data[0]

@router.delete("/models/{model_id}")
def delete_model(model_id: str, user=Depends(require_admin)):
    supabase_admin.table("models").delete().eq("id", model_id).execute()
    return {"deleted": True}

# ============================================================
# PRODUCTS
# ============================================================
class ProductBody(BaseModel):
    model_id: Optional[str] = None
    product_id: Optional[str] = None
    description: Optional[str] = None
    hourly_rate: Optional[float] = None
    eq_factor: Optional[float] = None
    no_of_persons: Optional[int] = None
    pitch_time: Optional[float] = None
    te_time: Optional[float] = None
    man_time: Optional[float] = None
    machine_time: Optional[float] = None
    handling_unit: Optional[int] = None
    cost: Optional[float] = None
    product_type: Optional[str] = None
    cycle_time: Optional[float] = None
    is_active: Optional[bool] = None

@router.get("/products")
def get_products(
    model_id: Optional[str] = None,
    line_id: Optional[str] = None,
    user=Depends(get_current_user)
):
    q = supabase_admin.table("product_master").select("*").order("product_id")
    if model_id:
        q = q.eq("model_id", model_id)
    elif line_id:
        # Get models for this line first
        models = supabase_admin.table("models").select("id").eq("line_id", line_id).execute().data
        model_ids = [m["id"] for m in models]
        if not model_ids:
            return []
        q = q.in_("model_id", model_ids)
    return q.execute().data

@router.post("/products")
def create_product(body: ProductBody, user=Depends(require_admin)):
    if not body.model_id or not body.product_id:
        raise HTTPException(status_code=400, detail="model_id and product_id required")
    data = {k: v for k, v in body.dict().items() if v is not None}
    res = supabase_admin.table("product_master").insert(data).execute()
    return res.data[0]

@router.put("/products/{product_id}")
def update_product(product_id: str, body: ProductBody, user=Depends(require_admin)):
    data = {k: v for k, v in body.dict().items() if v is not None}
    res = supabase_admin.table("product_master").update(data).eq("id", product_id).execute()
    return res.data[0]

@router.delete("/products/{product_id}")
def delete_product(product_id: str, user=Depends(require_admin)):
    supabase_admin.table("product_master").delete().eq("id", product_id).execute()
    return {"deleted": True}

# ============================================================
# SHIFTS
# ============================================================
class ShiftBody(BaseModel):
    name: Optional[str] = None
    start_time: Optional[str] = None
    end_time: Optional[str] = None
    is_active: Optional[bool] = None

@router.get("/shifts")
def get_shifts(user=Depends(get_current_user)):
    return supabase_admin.table("shifts").select("*").order("start_time").execute().data

@router.post("/shifts")
def create_shift(body: ShiftBody, user=Depends(require_admin)):
    if not body.name or not body.start_time or not body.end_time:
        raise HTTPException(status_code=400, detail="name, start_time, end_time required")
    data = {k: v for k, v in body.dict().items() if v is not None}
    res = supabase_admin.table("shifts").insert(data).execute()
    return res.data[0]

@router.put("/shifts/{shift_id}")
def update_shift(shift_id: str, body: ShiftBody, user=Depends(require_admin)):
    data = {k: v for k, v in body.dict().items() if v is not None}
    res = supabase_admin.table("shifts").update(data).eq("id", shift_id).execute()
    return res.data[0]

@router.delete("/shifts/{shift_id}")
def delete_shift(shift_id: str, user=Depends(require_admin)):
    supabase_admin.table("shifts").delete().eq("id", shift_id).execute()
    return {"deleted": True}

# ============================================================
# DOWNTIME REASONS
# ============================================================
class ReasonBody(BaseModel):
    reason: Optional[str] = None
    category: Optional[str] = None
    is_active: Optional[bool] = None

@router.get("/reasons")
def get_reasons(user=Depends(get_current_user)):
    return supabase_admin.table("downtime_reasons").select("*").order("reason").execute().data

@router.post("/reasons")
def create_reason(body: ReasonBody, user=Depends(require_admin)):
    if not body.reason:
        raise HTTPException(status_code=400, detail="reason required")
    data = {k: v for k, v in body.dict().items() if v is not None}
    res = supabase_admin.table("downtime_reasons").insert(data).execute()
    return res.data[0]

@router.put("/reasons/{reason_id}")
def update_reason(reason_id: str, body: ReasonBody, user=Depends(require_admin)):
    data = {k: v for k, v in body.dict().items() if v is not None}
    res = supabase_admin.table("downtime_reasons").update(data).eq("id", reason_id).execute()
    return res.data[0]

@router.delete("/reasons/{reason_id}")
def delete_reason(reason_id: str, user=Depends(require_admin)):
    supabase_admin.table("downtime_reasons").delete().eq("id", reason_id).execute()
    return {"deleted": True}

# ============================================================
# USERS (admin only)
# ============================================================
class UserUpdateBody(BaseModel):
    name: Optional[str] = None
    role: Optional[str] = None
    is_active: Optional[bool] = None

@router.get("/users")
def get_users(user=Depends(require_admin)):
    return supabase_admin.table("user_profiles").select("*").order("name").execute().data

@router.put("/users/{user_id}")
def update_user(user_id: str, body: UserUpdateBody, user=Depends(require_admin)):
    if body.role and body.role not in ("admin", "operator", "viewer"):
        raise HTTPException(status_code=400, detail="Invalid role")
    data = {k: v for k, v in body.dict().items() if v is not None}
    res = supabase_admin.table("user_profiles").update(data).eq("id", user_id).execute()
    return res.data[0]

@router.delete("/users/{user_id}")
def delete_user(user_id: str, user=Depends(require_admin)):
    supabase_admin.auth.admin.delete_user(user_id)
    supabase_admin.table("user_profiles").delete().eq("id", user_id).execute()
    return {"deleted": True}
