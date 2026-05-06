from fastapi import APIRouter, Depends, Query
from typing import Optional
from datetime import date, timedelta
from db import supabase_admin
from models.auth_deps import get_current_user

router = APIRouter()

def get_date_range(period: str):
    today = date.today()
    if period == "week":
        return str(today - timedelta(days=7)), str(today)
    elif period == "month":
        return str(today.replace(day=1)), str(today)
    else:  # today
        return str(today), str(today)


# ============================================================
# SUMMARY — dashboard KPIs + per-line breakdown
# ============================================================
@router.get("/summary")
def get_summary(
    period: str = "today",
    from_date: Optional[str] = None,
    to_date: Optional[str] = None,
    line_id: Optional[str] = None,
    user=Depends(get_current_user)
):
    if not from_date or not to_date:
        from_date, to_date = get_date_range(period)

    q = supabase_admin.table("production_entries").select(
        "output, target, manpower, hours_worked, line_id, lines(name)"
    ).gte("date", from_date).lte("date", to_date)

    if line_id:
        q = q.eq("line_id", line_id)

    entries = q.execute().data

    # Total downtime in range
    dt_q = supabase_admin.table("downtime_entries").select(
        "duration_minutes, production_entries!inner(date)"
    )
    dt_data = dt_q.execute().data
    total_dt = sum(d["duration_minutes"] for d in dt_data if
                   from_date <= (d.get("production_entries") or {}).get("date", "") <= to_date)

    # Aggregate per line
    lines_map = {}
    for e in entries:
        lid = e["line_id"]
        lname = (e.get("lines") or {}).get("name", "—")
        if lid not in lines_map:
            lines_map[lid] = {"line_id": lid, "line_name": lname, "output": 0, "target": 0, "manpower": 0}
        lines_map[lid]["output"]   += e["output"]
        lines_map[lid]["target"]   += e["target"]
        lines_map[lid]["manpower"] += e["manpower"]

    total_output = sum(e["output"] for e in entries)
    total_target = sum(e["target"] for e in entries)

    return {
        "total_output": total_output,
        "total_target": total_target,
        "total_downtime_mins": total_dt,
        "efficiency": round(total_output / total_target * 100, 1) if total_target else 0,
        "lines": list(lines_map.values()),
    }


# ============================================================
# HOURLY TREND
# ============================================================
@router.get("/hourly-trend")
def get_hourly_trend(
    entry_date: Optional[str] = None,
    line_id: Optional[str] = None,
    user=Depends(get_current_user)
):
    d = entry_date or str(date.today())
    q = supabase_admin.table("production_entries").select(
        "output, target, shift_id, shifts(name, start_time)"
    ).eq("date", d)
    if line_id:
        q = q.eq("line_id", line_id)

    entries = q.execute().data

    # Aggregate by shift
    shift_map = {}
    for e in entries:
        s = e.get("shifts") or {}
        key = s.get("start_time", "?")
        label = s.get("name", key)
        if key not in shift_map:
            shift_map[key] = {"hour": label, "output": 0, "target": 0}
        shift_map[key]["output"] += e["output"]
        shift_map[key]["target"] += e["target"]

    return sorted(shift_map.values(), key=lambda x: x["hour"])


# ============================================================
# DOWNTIME BREAKDOWN
# ============================================================
@router.get("/downtime")
def get_downtime_breakdown(
    period: str = "today",
    from_date: Optional[str] = None,
    to_date: Optional[str] = None,
    line_id: Optional[str] = None,
    user=Depends(get_current_user)
):
    if not from_date or not to_date:
        from_date, to_date = get_date_range(period)

    # Get entry IDs in range
    q = supabase_admin.table("production_entries").select("id").gte("date", from_date).lte("date", to_date)
    if line_id:
        q = q.eq("line_id", line_id)
    entry_ids = [e["id"] for e in q.execute().data]

    if not entry_ids:
        return []

    dt = supabase_admin.table("downtime_entries").select(
        "duration_minutes, downtime_reasons(reason, category)"
    ).in_("production_entry_id", entry_ids).execute().data

    # Aggregate by reason
    reasons_map = {}
    for d in dt:
        r = (d.get("downtime_reasons") or {})
        key = r.get("reason", "Unknown")
        reasons_map[key] = reasons_map.get(key, 0) + d["duration_minutes"]

    return [{"reason": k, "minutes": v} for k, v in sorted(reasons_map.items(), key=lambda x: -x[1])]


# ============================================================
# MANPOWER UTILIZATION
# ============================================================
@router.get("/manpower")
def get_manpower(
    period: str = "today",
    from_date: Optional[str] = None,
    to_date: Optional[str] = None,
    user=Depends(get_current_user)
):
    if not from_date or not to_date:
        from_date, to_date = get_date_range(period)

    entries = supabase_admin.table("production_entries").select(
        "output, manpower, hours_worked, line_id, lines(name)"
    ).gte("date", from_date).lte("date", to_date).execute().data

    lines_map = {}
    for e in entries:
        lid = e["line_id"]
        lname = (e.get("lines") or {}).get("name", "—")
        if lid not in lines_map:
            lines_map[lid] = {"line_name": lname, "output": 0, "manpower": 0, "hours": 0, "count": 0}
        lines_map[lid]["output"]   += e["output"]
        lines_map[lid]["manpower"] += e["manpower"]
        lines_map[lid]["hours"]    += e["hours_worked"]
        lines_map[lid]["count"]    += 1

    result = []
    for v in lines_map.values():
        days = v["hours"] / 8 if v["hours"] else 1
        upmd = round(v["output"] / v["manpower"] / days, 2) if v["manpower"] else 0
        result.append({
            "line_name": v["line_name"],
            "manpower": v["manpower"],
            "output": v["output"],
            "units_per_man_day": upmd,
        })

    return result


# ============================================================
# DAILY TREND
# ============================================================
@router.get("/daily-trend")
def get_daily_trend(
    from_date: Optional[str] = None,
    to_date: Optional[str] = None,
    line_id: Optional[str] = None,
    user=Depends(get_current_user)
):
    today = date.today()
    fd = from_date or str(today - timedelta(days=29))
    td = to_date or str(today)

    q = supabase_admin.table("production_entries").select(
        "date, output, target"
    ).gte("date", fd).lte("date", td).order("date")
    if line_id:
        q = q.eq("line_id", line_id)

    entries = q.execute().data

    # Aggregate by date
    date_map = {}
    for e in entries:
        d = e["date"]
        if d not in date_map:
            date_map[d] = {"date": d, "output": 0, "target": 0}
        date_map[d]["output"] += e["output"]
        date_map[d]["target"] += e["target"]

    return sorted(date_map.values(), key=lambda x: x["date"])


# ============================================================
# MONTHLY SUMMARY TABLE
# ============================================================
@router.get("/monthly-summary")
def get_monthly_summary(
    year: Optional[int] = None,
    month: Optional[int] = None,
    user=Depends(get_current_user)
):
    today = date.today()
    y = year or today.year
    m = month or today.month

    from_date = f"{y}-{m:02d}-01"
    # Last day of month
    if m == 12:
        to_date = f"{y+1}-01-01"
    else:
        to_date = f"{y}-{m+1:02d}-01"

    entries = supabase_admin.table("production_entries").select(
        "date, output, target, manpower, hours_worked, line_id, model_id, "
        "lines(name), models(name)"
    ).gte("date", from_date).lt("date", to_date).execute().data

    # Aggregate by line + model
    summary = {}
    for e in entries:
        lid = e["line_id"]
        mid = e["model_id"]
        key = f"{lid}::{mid}"
        if key not in summary:
            summary[key] = {
                "line_name": (e.get("lines") or {}).get("name", "—"),
                "model_name": (e.get("models") or {}).get("name", "—"),
                "total_output": 0,
                "total_target": 0,
                "total_manpower": 0,
                "total_hours": 0,
                "days": 0,
            }
        summary[key]["total_output"]   += e["output"]
        summary[key]["total_target"]   += e["target"]
        summary[key]["total_manpower"] += e["manpower"]
        summary[key]["total_hours"]    += e["hours_worked"]
        summary[key]["days"]           += 1

    result = []
    for v in summary.values():
        eff = round(v["total_output"] / v["total_target"] * 100, 1) if v["total_target"] else 0
        days = v["total_hours"] / 8 if v["total_hours"] else 1
        upmd = round(v["total_output"] / v["total_manpower"] / days, 2) if v["total_manpower"] else 0
        result.append({
            **v,
            "efficiency": eff,
            "units_per_man_day": upmd,
        })

    return sorted(result, key=lambda x: (x["line_name"], x["model_name"]))


# ============================================================
# EFFICIENCY / PRODUCTIVITY
# ============================================================
@router.get("/efficiency")
def get_efficiency(
    period: str = "month",
    line_id: Optional[str] = None,
    user=Depends(get_current_user)
):
    from_date, to_date = get_date_range(period)

    q = supabase_admin.table("production_entries").select(
        "output, target, manpower, hours_worked, date, line_id, lines(name)"
    ).gte("date", from_date).lte("date", to_date)
    if line_id:
        q = q.eq("line_id", line_id)

    entries = q.execute().data

    lines_map = {}
    for e in entries:
        lid = e["line_id"]
        lname = (e.get("lines") or {}).get("name", "—")
        if lid not in lines_map:
            lines_map[lid] = {"line_name": lname, "output": 0, "target": 0, "manpower": 0, "hours": 0}
        lines_map[lid]["output"]   += e["output"]
        lines_map[lid]["target"]   += e["target"]
        lines_map[lid]["manpower"] += e["manpower"]
        lines_map[lid]["hours"]    += e["hours_worked"]

    result = []
    for v in lines_map.values():
        eff  = round(v["output"] / v["target"] * 100, 1) if v["target"] else 0
        days = v["hours"] / 8 if v["hours"] else 1
        upmd = round(v["output"] / v["manpower"] / days, 2) if v["manpower"] else 0
        result.append({
            "line_name": v["line_name"],
            "efficiency": eff,
            "units_per_man_day": upmd,
            "total_output": v["output"],
            "total_target": v["target"],
        })

    return sorted(result, key=lambda x: -x["efficiency"])
