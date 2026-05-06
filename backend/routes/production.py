from fastapi import APIRouter, HTTPException, Depends, Query
from pydantic import BaseModel
from typing import Optional, List
from datetime import date, datetime
from db import supabase_admin
from models.auth_deps import get_current_user, require_operator_or_admin, require_admin

router = APIRouter()

class DowntimeItem(BaseModel):
    reason_id: str
    duration_minutes: int
    remarks: Optional[str] = None

class ProductionEntryCreate(BaseModel):
    date: date
    line_id: str
    model_id: str
    product_id: Optional[str] = None
    shift_id: str
    target: int
    output: int
    manpower: int
    hours_worked: float = 8.0
    downtime: Optional[List[DowntimeItem]] = []

class ProductionEntryUpdate(BaseModel):
    target: Optional[int] = None
    output: Optional[int] = None
    manpower: Optional[int] = None
    hours_worked: Optional[float] = None


@router.get("/entries")
def get_entries(
    from_date: Optional[str] = Query(None, alias="from"),
    to_date: Optional[str] = Query(None, alias="to"),
    line_id: Optional[str] = None,
    model_id: Optional[str] = None,
    user=Depends(get_current_user)
):
    q = supabase_admin.table("production_entries").select(
        "*, lines(name), models(name), shifts(name, start_time, end_time), "
        "user_profiles(name)"
    ).order("date", desc=True).order("created_at", desc=True)

    if from_date:
        q = q.gte("date", from_date)
    if to_date:
        q = q.lte("date", to_date)
    if line_id:
        q = q.eq("line_id", line_id)
    if model_id:
        q = q.eq("model_id", model_id)

    # Operators only see own entries
    if user["role"] == "operator":
        q = q.eq("entered_by", user["id"])

    rows = q.execute().data

    # Flatten and compute downtime
    result = []
    for row in rows:
        entry_id = row["id"]
        dt_res = supabase_admin.table("downtime_entries").select(
            "duration_minutes, downtime_reasons(reason)"
        ).eq("production_entry_id", entry_id).execute().data

        total_dt = sum(d["duration_minutes"] for d in dt_res)

        result.append({
            **row,
            "line_name":  row.get("lines", {}).get("name", "—") if row.get("lines") else "—",
            "model_name": row.get("models", {}).get("name", "—") if row.get("models") else "—",
            "shift_name": row.get("shifts", {}).get("name", "—") if row.get("shifts") else "—",
            "entered_by_name": row.get("user_profiles", {}).get("name", "—") if row.get("user_profiles") else "—",
            "total_downtime_mins": total_dt,
        })

    return result


@router.post("/entries")
def create_entry(body: ProductionEntryCreate, user=Depends(require_operator_or_admin)):
    entry_data = {
        "date": str(body.date),
        "line_id": body.line_id,
        "model_id": body.model_id,
        "product_id": body.product_id,
        "shift_id": body.shift_id,
        "target": body.target,
        "output": body.output,
        "manpower": body.manpower,
        "hours_worked": body.hours_worked,
        "entered_by": user["id"],
    }

    entry_res = supabase_admin.table("production_entries").insert(entry_data).execute()
    entry = entry_res.data[0]

    # Insert downtime rows if any
    if body.downtime:
        dt_rows = [
            {
                "production_entry_id": entry["id"],
                "reason_id": d.reason_id,
                "duration_minutes": d.duration_minutes,
                "remarks": d.remarks,
            }
            for d in body.downtime
        ]
        supabase_admin.table("downtime_entries").insert(dt_rows).execute()

    return entry


@router.put("/entries/{entry_id}")
def update_entry(entry_id: str, body: ProductionEntryUpdate, user=Depends(get_current_user)):
    # Check ownership for operators
    if user["role"] == "operator":
        existing = supabase_admin.table("production_entries").select("entered_by,date").eq("id", entry_id).single().execute().data
        if not existing:
            raise HTTPException(status_code=404, detail="Entry not found")
        if existing["entered_by"] != user["id"]:
            raise HTTPException(status_code=403, detail="Cannot edit another operator's entry")
        if existing["date"] != str(date.today()):
            raise HTTPException(status_code=403, detail="Can only edit today's entries")

    data = {k: v for k, v in body.dict().items() if v is not None}
    data["updated_at"] = datetime.utcnow().isoformat()
    res = supabase_admin.table("production_entries").update(data).eq("id", entry_id).execute()
    return res.data[0]


@router.delete("/entries/{entry_id}")
def delete_entry(entry_id: str, user=Depends(require_admin)):
    supabase_admin.table("downtime_entries").delete().eq("production_entry_id", entry_id).execute()
    supabase_admin.table("production_entries").delete().eq("id", entry_id).execute()
    return {"deleted": True}


# ============================================================
# DOWNTIME for a specific entry
# ============================================================
@router.get("/entries/{entry_id}/downtime")
def get_entry_downtime(entry_id: str, user=Depends(get_current_user)):
    res = supabase_admin.table("downtime_entries").select(
        "*, downtime_reasons(reason, category)"
    ).eq("production_entry_id", entry_id).execute()
    return res.data

@router.post("/downtime")
def add_downtime(body: DowntimeItem, entry_id: str, user=Depends(require_operator_or_admin)):
    res = supabase_admin.table("downtime_entries").insert({
        "production_entry_id": entry_id,
        "reason_id": body.reason_id,
        "duration_minutes": body.duration_minutes,
        "remarks": body.remarks,
    }).execute()
    return res.data[0]

@router.delete("/downtime/{downtime_id}")
def delete_downtime(downtime_id: str, user=Depends(require_admin)):
    supabase_admin.table("downtime_entries").delete().eq("id", downtime_id).execute()
    return {"deleted": True}
