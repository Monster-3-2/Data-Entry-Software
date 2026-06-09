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
    shift_id: Optional[str] = None,
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
    if shift_id:
        q = q.eq("shift_id", shift_id)

    # Operators only see own entries
    if user["role"] == "operator":
        q = q.eq("entered_by", user["id"])

    rows = q.execute().data

    # Flatten and compute downtime
    # ONE batch query for all downtime instead of one per row
    all_entry_ids = [row["id"] for row in rows]
    dt_all = []
    if all_entry_ids:
        dt_all = supabase_admin.table("downtime_entries").select(
            "production_entry_id, duration_minutes"
        ).in_("production_entry_id", all_entry_ids).execute().data
    
    # Build a lookup dict: entry_id -> total downtime minutes
    dt_map = {}
    for d in dt_all:
        eid = d["production_entry_id"]
        dt_map[eid] = dt_map.get(eid, 0) + d["duration_minutes"]
    
    # Now build result without any extra DB calls
    result = []
    for row in rows:
        result.append({
            **row,
            "line_name":  row.get("lines", {}).get("name", "—") if row.get("lines") else "—",
            "model_name": row.get("models", {}).get("name", "—") if row.get("models") else "—",
            "shift_name": row.get("shifts", {}).get("name", "—") if row.get("shifts") else "—",
            "entered_by_name": row.get("user_profiles", {}).get("name", "—") if row.get("user_profiles") else "—",
            "total_downtime_mins": dt_map.get(row["id"], 0),
        })

    return result


@router.post("/entries")
def create_entry(body: ProductionEntryCreate, user=Depends(require_operator_or_admin)):
    # ── Duplicate guard: blocked only when ALL FOUR match — Line + Model + Shift + Date.
    #    Same line + different model + same shift = ALLOWED.
    #    Different line + same model + same shift = ALLOWED.
    existing = supabase_admin.table("production_entries") \
        .select("id") \
        .eq("date", str(body.date)) \
        .eq("line_id", body.line_id) \
        .eq("model_id", body.model_id) \
        .eq("shift_id", body.shift_id) \
        .execute().data
    if existing:
        raise HTTPException(
            status_code=409,
            detail="Duplicate entry: same Line + Model + Shift + Date combination already exists."
        )

    # Operator role: target must come from product master (cannot be manually set)
    if user["role"] == "operator" and body.product_id:
        product = supabase_admin.table("product_master").select("hourly_rate").eq("id", body.product_id).single().execute().data
        if product and product.get("hourly_rate"):
            auto_target = round(product["hourly_rate"] * (body.hours_worked or 1))
        else:
            auto_target = body.target  # no master data, use submitted
        target_val = auto_target
    else:
        target_val = body.target

    entry_data = {
        "date": str(body.date),
        "line_id": body.line_id,
        "model_id": body.model_id,
        "product_id": body.product_id,
        "shift_id": body.shift_id,
        "target": target_val,
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
    role = user["role"]
    # operator (restricted): cannot edit entries at all
    if role == "operator":
        raise HTTPException(status_code=403, detail="Operators cannot edit entries. Contact your Product Lead.")
    # product_lead: can only edit own entries from today
    if role == "product_lead":
        existing = supabase_admin.table("production_entries").select("entered_by,date,target").eq("id", entry_id).single().execute().data
        if not existing:
            raise HTTPException(status_code=404, detail="Entry not found")
        if existing["entered_by"] != user["id"]:
            raise HTTPException(status_code=403, detail="Cannot edit another person's entry")
        if existing["date"] != str(date.today()):
            raise HTTPException(status_code=403, detail="Can only edit today's entries")
        # product_lead cannot change target — strip it from update
        body_dict = {k: v for k, v in body.dict().items() if v is not None}
        body_dict.pop("target", None)
        body_dict["updated_at"] = datetime.utcnow().isoformat()
        res = supabase_admin.table("production_entries").update(body_dict).eq("id", entry_id).execute()
        return res.data[0]

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
