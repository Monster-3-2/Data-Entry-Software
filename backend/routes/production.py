from fastapi import APIRouter, HTTPException, Depends, Query
from pydantic import BaseModel
from typing import Optional, List
from datetime import date, datetime
from db import supabase_admin
from models.auth_deps import get_current_user, require_operator_or_admin, require_admin

router = APIRouter()

class DowntimeItem(BaseModel):
    reason_id: str
    start_time: Optional[str] = None        # "HH:MM" e.g. "09:30" — from time-range mode
    end_time: Optional[str] = None          # "HH:MM" e.g. "10:00" — from time-range mode
    duration_minutes: Optional[int] = None  # direct minutes — from duration mode or pre-computed
    remarks: Optional[str] = None

    def computed_minutes(self) -> int:
        """Priority: start+end time range → direct duration_minutes."""
        if self.start_time and self.end_time:
            def to_min(t):
                h, m = map(int, t.split(':'))
                return h * 60 + m
            diff = to_min(self.end_time) - to_min(self.start_time)
            if diff < 0:
                diff += 24 * 60  # overnight
            return max(diff, 0)
        # Duration-only mode: duration_minutes already set by frontend
        return self.duration_minutes or 0

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
    # Batch downtime query — chunk to avoid URL length limits with many IDs
    all_entry_ids = [row["id"] for row in rows]
    dt_all = []
    if all_entry_ids:
        CHUNK = 50  # safe chunk size for Supabase in_() URL length
        for i in range(0, len(all_entry_ids), CHUNK):
            chunk = all_entry_ids[i:i+CHUNK]
            try:
                chunk_data = supabase_admin.table("downtime_entries").select(
                    "production_entry_id, duration_minutes, remarks, downtime_reasons(reason)"
                ).in_("production_entry_id", chunk).execute().data
                dt_all.extend(chunk_data or [])
            except Exception as e:
                print(f"[WARN] Downtime batch query chunk {i} failed: {e}")

    # Build lookup dicts: entry_id -> total minutes, and entry_id -> list of breakdown rows
    dt_map = {}
    dt_detail_map = {}
    for d in dt_all:
        eid = d["production_entry_id"]
        dt_map[eid] = dt_map.get(eid, 0) + (d["duration_minutes"] or 0)
        dt_detail_map.setdefault(eid, []).append({
            "reason":           (d.get("downtime_reasons") or {}).get("reason", "Unknown"),
            "duration_minutes": d.get("duration_minutes") or 0,
            "remarks":          d.get("remarks") or "",
        })
    
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
            "downtime_detail": dt_detail_map.get(row["id"], []),
        })
    return result


@router.post("/entries")
def create_entry(body: ProductionEntryCreate, user=Depends(require_operator_or_admin)):
    # ── Duplicate guard: blocked only when ALL FOUR match — Line + Model + Shift + Date.
    #    Same line + different model + same shift = ALLOWED.
    #    Different line + same model + same shift = ALLOWED.
    existing = supabase_admin.table("production_entries") \
        .select("id, hours_worked") \
        .eq("date", str(body.date)) \
        .eq("line_id", body.line_id) \
        .eq("model_id", body.model_id) \
        .eq("shift_id", body.shift_id) \
        .execute().data
    if existing:
        # Allow partial entries in same hour slot — block only when total minutes >= 60
        total_minutes = sum((e.get("hours_worked") or 0) * 60 for e in existing)
        new_minutes   = (body.hours_worked or 0) * 60
        if total_minutes + new_minutes > 60:
            raise HTTPException(
                status_code=409,
                detail=f"Hour slot full: {int(total_minutes)} min already recorded. Cannot add {int(new_minutes)} more (max 60 min per slot)."
            )

    # Operator role: target must come from product master (cannot be manually set)
    # Operator role: target must come from product master (cannot be manually set)
    if user["role"] == "operator" and body.product_id:
        import json
        product = supabase_admin.table("product_master") \
            .select("hourly_rate, persons_rate_json") \
            .eq("id", body.product_id).single().execute().data
        matched_rate = None
        if product:
            # First: try persons_rate_json — match by manpower typed by operator
            if product.get("persons_rate_json"):
                try:
                    rate_rows = json.loads(product["persons_rate_json"])
                    row = next((r for r in rate_rows if int(r["persons"]) == body.manpower), None)
                    if row:
                        matched_rate = float(row["rate"])
                except Exception:
                    pass
            # Fallback: use hourly_rate (old single-value field)
            if matched_rate is None and product.get("hourly_rate"):
                matched_rate = float(product["hourly_rate"])
        target_val = round(matched_rate * (body.hours_worked or 8)) if matched_rate else body.target
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
                "duration_minutes": d.computed_minutes(),
                "remarks": d.remarks,
                # start_time/end_time omitted — columns not in live DB
                # Run the schema migration to add them if needed
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
def delete_entry(entry_id: str, user=Depends(get_current_user)):
    role = user["role"]
    today = str(date.today())

    # Fetch entry to check ownership and date
    if role not in ("admin",):
        existing = supabase_admin.table("production_entries").select("entered_by, date").eq("id", entry_id).single().execute().data
        if not existing:
            raise HTTPException(status_code=404, detail="Entry not found")

        if role == "product_lead":
            # Allow delete for entries within last 7 days
            entry_date = existing["date"]
            from datetime import timedelta
            cutoff = str(date.today() - timedelta(days=7))
            if entry_date < cutoff:
                raise HTTPException(status_code=403, detail="Product leads can only delete entries from the last 7 days.")
        elif role == "operator":
            # Allow delete for own entries from today only
            if existing["date"] != today:
                raise HTTPException(status_code=403, detail="Operators can only delete today's entries.")
            if existing["entered_by"] != user["id"]:
                raise HTTPException(status_code=403, detail="Operators can only delete their own entries.")
        else:
            raise HTTPException(status_code=403, detail="Insufficient permissions.")

    supabase_admin.table("downtime_entries").delete().eq("production_entry_id", entry_id).execute()
    supabase_admin.table("production_entries").delete().eq("id", entry_id).execute()
    return {"deleted": True}


# ============================================================
# DOWNTIME for a specific entry
# ============================================================
@router.get("/entries/{entry_id}/downtime")
def get_entry_downtime(entry_id: str, user=Depends(get_current_user)):
    res = supabase_admin.table("downtime_entries").select(
        "id, duration_minutes, remarks, downtime_reasons(reason, category)"
    ).eq("production_entry_id", entry_id).execute()
    return res.data

@router.post("/downtime")
def add_downtime(body: DowntimeItem, entry_id: str, user=Depends(require_operator_or_admin)):
    res = supabase_admin.table("downtime_entries").insert({
        "production_entry_id": entry_id,
        "reason_id": body.reason_id,
        "duration_minutes": body.computed_minutes(),
        "remarks": body.remarks,
    }).execute()
    return res.data[0]

class DowntimeUpdate(BaseModel):
    reason_id: Optional[str] = None
    start_time: Optional[str] = None
    end_time: Optional[str] = None
    duration_minutes: Optional[int] = None
    remarks: Optional[str] = None

@router.put("/downtime/{downtime_id}")
def update_downtime(downtime_id: str, body: DowntimeUpdate, user=Depends(get_current_user)):
    if user["role"] not in ("admin", "product_lead"):
        raise HTTPException(status_code=403, detail="Only admins and product leads can edit downtime entries.")
    # Only update supported fields (start_time/end_time not in live DB)
    allowed = {"reason_id", "duration_minutes", "remarks"}
    data = {k: v for k, v in body.dict().items() if v is not None and k in allowed}
    res = supabase_admin.table("downtime_entries").update(data).eq("id", downtime_id).execute()
    return res.data[0]

@router.delete("/downtime/{downtime_id}")
def delete_downtime(downtime_id: str, user=Depends(get_current_user)):
    if user["role"] not in ("admin", "product_lead"):
        raise HTTPException(status_code=403, detail="Only admins and product leads can delete downtime entries.")
    supabase_admin.table("downtime_entries").delete().eq("id", downtime_id).execute()
    return {"deleted": True}
