from fastapi import APIRouter, Depends, Query
from typing import Optional, List
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


def _upmd_for_line(entries_for_line: list) -> float:
    """
    UPMD formula: (total hourly-equivalent output) / avg_manpower_per_line
    - Each entry's output is first normalised to per-hour: entry_output / entry_hours_worked
    - Then all normalised outputs are summed and divided by the mean manpower.
    This handles split-hour entries correctly (30-min entry at 14 units → 28 u/hr, not 14).
    """
    valid = [e for e in entries_for_line if (e.get("manpower") or 0) > 0 and (e.get("hours_worked") or 0) > 0]
    if not valid:
        # Fallback: if hours_worked missing, use raw output / avg_manpower
        fallback = [e for e in entries_for_line if (e.get("manpower") or 0) > 0]
        if not fallback:
            return 0.0
        total_output = sum(e["output"] for e in fallback)
        avg_manpower = sum(e["manpower"] for e in fallback) / len(fallback)
        return round(total_output / avg_manpower, 2) if avg_manpower else 0.0
    # Normalise each entry's output to hourly rate, then average across entries
    hourly_outputs = [e["output"] / e["hours_worked"] for e in valid]
    avg_hourly_out = sum(hourly_outputs) / len(hourly_outputs)
    avg_manpower   = sum(e["manpower"] for e in valid) / len(valid)
    if avg_manpower == 0:
        return 0.0
    return round(avg_hourly_out / avg_manpower, 2)


def _manpower_for_slot(elist: list) -> int:
    """
    For a SINGLE time slot (one hour, one shift) with multiple lines:
    return total manpower = sum of modal manpower per line.
    Each line has an independent crew; modal avoids inflation from repeated hourly entries.
    """
    from collections import Counter, defaultdict
    line_groups: dict = defaultdict(list)
    for e in elist:
        if (e.get("manpower") or 0) > 0:
            line_groups[e.get("line_id", "?")].append(e["manpower"])
    total = 0
    for mp_list in line_groups.values():
        c = Counter(mp_list)
        total += c.most_common(1)[0][0]
    return total


def _manpower_for_period(entries: list) -> int:
    """
    For a MULTI-SHIFT period (day / week / month):
    Different shifts on the same line have different crews (First Shift 12, Second Shift 10 → 22 for the day).
    So we CANNOT take modal across all entries for a line — that would pick whichever crew size appeared most.

    Correct approach:
      1. Group entries by (line_id, date, shift_group_id) → each group is one crew working one shift on one day.
      2. Modal manpower within each group = representative crew size for that shift.
      3. Sum all groups → total manpower across all shifts and days.

    Since shift_group_id is not in the entries fetched by period-breakdown (we only select line_id, date,
    manpower, hours_worked, output, target), we use shift_id as the grouping key instead — each shift slot
    is a distinct crew assignment.
    """
    from collections import Counter, defaultdict
    # Key: (line_id, date, shift_id) → one unique crew-shift-day
    group_map: dict = defaultdict(list)
    for e in entries:
        if (e.get("manpower") or 0) > 0:
            key = (e.get("line_id", "?"), e.get("date", "?"), e.get("shift_id", "?"))
            group_map[key].append(e["manpower"])
    total = 0
    for mp_list in group_map.values():
        c = Counter(mp_list)
        total += c.most_common(1)[0][0]
    return total


def _apply_line_filter(q, line_id: Optional[str], line_ids: Optional[str]):
    """Apply single or multi-line filter to a supabase query."""
    if line_ids:
        ids = [i.strip() for i in line_ids.split(',') if i.strip()]
        if ids:
            return q.in_("line_id", ids)
    elif line_id:
        return q.eq("line_id", line_id)
    return q


def _fetch_all(q, page_size: int = 1000) -> list:
    """
    Fetch all rows from a Supabase query using pagination.
    Supabase default limit is 1000 rows — silently truncates beyond that.
    This paginates until we get fewer rows than page_size (meaning we're done).
    """
    all_rows = []
    offset   = 0
    while True:
        batch = q.range(offset, offset + page_size - 1).execute().data
        if not batch:
            break
        all_rows.extend(batch)
        if len(batch) < page_size:
            break          # last page — we have everything
        offset += page_size
    return all_rows


# ============================================================
# SUMMARY — dashboard KPIs + per-line breakdown
# ============================================================
@router.get("/summary")
def get_summary(
    period: str = "today",
    from_date: Optional[str] = None,
    to_date: Optional[str] = None,
    line_id: Optional[str] = None,
    line_ids: Optional[str] = None,   # comma-separated for multi-line
    shift_id: Optional[str] = None,
    user=Depends(get_current_user)
):
    if not from_date or not to_date:
        from_date, to_date = get_date_range(period)

    q = supabase_admin.table("production_entries").select(
        "id, output, target, manpower, hours_worked, line_id, model_id, lines(name), models(name)"
    ).gte("date", from_date).lte("date", to_date)
    q = _apply_line_filter(q, line_id, line_ids)
    if shift_id:
        q = q.eq("shift_id", shift_id)
    entries = _fetch_all(q)  # paginated — avoids 1000-row Supabase limit

    # Downtime total
    total_dt = 0
    if entries:
        entry_ids = [e["id"] for e in entries]
        for i in range(0, len(entry_ids), 100):
            chunk = entry_ids[i:i+100]
            try:
                dt_data = supabase_admin.table("downtime_entries").select(
                    "duration_minutes"
                ).in_("production_entry_id", chunk).execute().data
                total_dt += sum((d["duration_minutes"] or 0) for d in (dt_data or []))
            except Exception as e:
                print(f"[WARN] downtime chunk failed: {e}")

    # Group entries by line
    lines_entries: dict[str, list] = {}
    model_map: dict[str, dict] = {}
    for e in entries:
        lid   = e["line_id"]
        mid   = e.get("model_id", "")
        lname = (e.get("lines")  or {}).get("name", "—")
        mname = (e.get("models") or {}).get("name", "—")
        lines_entries.setdefault(lid, []).append(e)

        mk = f"{lid}::{mid}"
        if mk not in model_map:
            model_map[mk] = {"line_name": lname, "model_name": mname, "output": 0, "target": 0}
        model_map[mk]["output"] += e["output"]
        model_map[mk]["target"] += e["target"]

    from collections import Counter
    line_cards = []
    for lid, elist in lines_entries.items():
        lname  = (elist[0].get("lines") or {}).get("name", "—")
        models = [v for k, v in model_map.items() if k.startswith(lid + "::")]
        line_output  = sum(e["output"] for e in elist)
        valid_mp     = [e["manpower"] for e in elist if (e.get("manpower") or 0) > 0]
        # Modal manpower for this line (same crew repeated each hour — modal = representative)
        mp_counter   = Counter(valid_mp)
        line_manpower = mp_counter.most_common(1)[0][0] if mp_counter else 0
        line_upmd    = round(line_output / (sum(valid_mp) / len(valid_mp)), 2) if valid_mp else 0.0
        line_cards.append({
            "line_id":           lid,
            "line_name":         lname,
            "output":            line_output,
            "target":            sum(e["target"] for e in elist),
            "manpower":          line_manpower,
            "units_per_man_day": line_upmd,
            "models":            models,
        })

    total_output   = sum(e["output"] for e in entries)
    total_target   = sum(e["target"] for e in entries)
    # Overall UPMD: total output / sum of per-line modal manpower
    total_manpower = sum(c["manpower"] for c in line_cards)
    overall_upmd   = round(total_output / total_manpower, 2) if total_manpower > 0 else 0

    return {
        "total_output":        total_output,
        "total_target":        total_target,
        "total_manpower":      total_manpower,
        "total_downtime_mins": total_dt,
        "efficiency":          round(total_output / total_target * 100, 1) if total_target else 0,
        "units_per_man_day":   overall_upmd,
        "lines":               line_cards,
    }


# ============================================================
# HOURLY TREND  (groups by individual hour/shift slot)
# ============================================================
@router.get("/hourly-trend")
def get_hourly_trend(
    entry_date: Optional[str] = None,
    line_id: Optional[str] = None,
    line_ids: Optional[str] = None,   # comma-separated for multi-line
    shift_id: Optional[str] = None,
    user=Depends(get_current_user)
):
    d = entry_date or str(date.today())
    q = supabase_admin.table("production_entries").select(
        "output, target, manpower, hours_worked, line_id, shift_id, shifts(name, start_time)"
    ).eq("date", d)
    q = _apply_line_filter(q, line_id, line_ids)
    if shift_id:
        q = q.eq("shift_id", shift_id)
    entries = _fetch_all(q)

    # Group raw entries by hour slot
    slot_entries: dict = {}
    for e in entries:
        s     = e.get("shifts") or {}
        key   = s.get("start_time", "?")
        label = s.get("name", key)
        if key not in slot_entries:
            slot_entries[key] = {"label": label, "entries": []}
        slot_entries[key]["entries"].append(e)

    result = []
    for key, v in slot_entries.items():
        elist    = v["entries"]
        output   = sum(e["output"] for e in elist)
        target   = sum(e["target"] for e in elist)
        manpower = _manpower_for_slot(elist)
        # UPMD: use _upmd_for_line which normalises each entry's output to hourly rate
        upmd = _upmd_for_line(elist)
        result.append({"hour": v["label"], "output": output, "target": target, "upmd": upmd, "manpower": manpower})

    return sorted(result, key=lambda x: x["hour"])


# ============================================================
# DAILY LINE vs UPMD TABLE
# ============================================================
@router.get("/daily-upmd")
def get_daily_upmd(
    from_date: Optional[str] = None,
    to_date: Optional[str] = None,
    line_id: Optional[str] = None,
    user=Depends(get_current_user)
):
    """
    Returns daily UPMD per line for a date range.
    For each date+line, UPMD = mean of per-entry (output/manpower) across all models/hours.
    This is then presented as a table: rows = dates, columns = lines.
    """
    today = date.today()
    fd = from_date or str(today - timedelta(days=6))
    td = to_date   or str(today)

    q = supabase_admin.table("production_entries").select(
        "date, output, manpower, line_id, lines(name)"
    ).gte("date", fd).lte("date", td).order("date")
    if line_id:
        q = q.eq("line_id", line_id)
    entries = _fetch_all(q)

    # Collect unique dates and lines, and group entries by (date, line)
    all_dates:  set  = set()
    all_lines:  dict = {}   # line_id -> line_name
    cell_entries: dict = {} # (date, line_id) -> [entries]

    for e in entries:
        d   = e["date"]
        lid = e["line_id"]
        lname = (e.get("lines") or {}).get("name", "—")
        all_dates.add(d)
        all_lines[lid] = lname
        key = (d, lid)
        cell_entries.setdefault(key, []).append(e)

    sorted_dates = sorted(all_dates)
    sorted_lines = sorted(all_lines.items(), key=lambda x: x[1])  # sort by name

    rows = []
    for d in sorted_dates:
        row = {"date": d, "lines": {}}
        for lid, lname in sorted_lines:
            elist = cell_entries.get((d, lid), [])
            row["lines"][lid] = {
                "line_name": lname,
                "upmd":      _upmd_for_line(elist) if elist else None,
                "output":    sum(e["output"] for e in elist),
            }
        rows.append(row)

    return {
        "lines":      [{"id": lid, "name": lname} for lid, lname in sorted_lines],
        "rows":       rows,
    }


# ============================================================
# SHIFTWISE TREND  (groups by shift_group — Morning / Afternoon / Night)
# ============================================================
@router.get("/shiftwise-trend")
def get_shiftwise_trend(
    from_date: Optional[str] = None,
    to_date: Optional[str] = None,
    entry_date: Optional[str] = None,
    line_id: Optional[str] = None,
    line_ids: Optional[str] = None,   # comma-separated for multi-line
    user=Depends(get_current_user)
):
    """
    Groups entries by shift_group (Morning/Afternoon/Night), not by individual hour.
    UPMD = shift total output / avg manpower per line (as used on shop floor).
    """
    d   = entry_date or from_date or str(date.today())
    end = to_date or d

    q = supabase_admin.table("production_entries").select(
        "output, target, manpower, hours_worked, line_id, shift_id, shifts(name, start_time, shift_group_id, shift_groups(id, name))"
    ).gte("date", d).lte("date", end)
    q = _apply_line_filter(q, line_id, line_ids)
    entries = _fetch_all(q)

    # Build group_entries_map in one pass
    group_entries_map: dict = {}
    group_label_map:   dict = {}
    for e in entries:
        sh  = e.get("shifts") or {}
        sg  = sh.get("shift_groups") or {}
        key   = sg.get("id") or sh.get("shift_group_id") or sh.get("start_time", "?")
        label = sg.get("name") or sh.get("name", str(key))
        group_entries_map.setdefault(key, []).append(e)
        group_label_map[key] = label

    result = []
    for key, elist in group_entries_map.items():
        output   = sum(e["output"] for e in elist)
        target   = sum(e["target"] for e in elist)
        manpower = _manpower_for_slot(elist)
        # UPMD: normalised to hourly rate per person via _upmd_for_line
        upmd = _upmd_for_line(elist)
        result.append({
            "shift":    group_label_map[key],
            "output":   output,
            "target":   target,
            "manpower": manpower,
            "upmd":     upmd,
        })
    return result


# ============================================================
# DOWNTIME BREAKDOWN
# ============================================================
@router.get("/downtime")
def get_downtime_breakdown(
    period: str = "today",
    from_date: Optional[str] = None,
    to_date: Optional[str] = None,
    line_id: Optional[str] = None,
    line_ids: Optional[str] = None,
    shift_id: Optional[str] = None,
    user=Depends(get_current_user)
):
    if not from_date or not to_date:
        from_date, to_date = get_date_range(period)

    q = supabase_admin.table("production_entries").select("id") \
        .gte("date", from_date).lte("date", to_date)
    if line_id:
        q = q.eq("line_id", line_id)
    if shift_id:
        q = q.eq("shift_id", shift_id)
    entry_ids = [e["id"] for e in _fetch_all(q)]

    if not entry_ids:
        return []

    all_dt = []
    for i in range(0, len(entry_ids), 100):
        chunk = entry_ids[i:i+100]
        try:
            dt = supabase_admin.table("downtime_entries").select(
                "duration_minutes, downtime_reasons(reason, category)"
            ).in_("production_entry_id", chunk).execute().data
            all_dt.extend(dt or [])
        except Exception as e:
            print(f"[WARN] downtime chunk failed: {e}")

    reasons_map: dict = {}
    for d in all_dt:
        r   = (d.get("downtime_reasons") or {})
        key = r.get("reason", "Unknown")
        reasons_map[key] = reasons_map.get(key, 0) + (d["duration_minutes"] or 0)

    return [{"reason": k, "minutes": v} for k, v in sorted(reasons_map.items(), key=lambda x: -x[1])]


# ============================================================
# MANPOWER UTILIZATION  (correct UPMD = mean of per-entry output/manpower)
# ============================================================
@router.get("/manpower")
def get_manpower(
    period: str = "today",
    from_date: Optional[str] = None,
    to_date: Optional[str] = None,
    line_id: Optional[str] = None,
    line_ids: Optional[str] = None,
    shift_id: Optional[str] = None,
    user=Depends(get_current_user)
):
    if not from_date or not to_date:
        from_date, to_date = get_date_range(period)

    q = supabase_admin.table("production_entries").select(
        "output, manpower, hours_worked, line_id, lines(name)"
    ).gte("date", from_date).lte("date", to_date)
    q = _apply_line_filter(q, line_id, line_ids)
    if shift_id:
        q = q.eq("shift_id", shift_id)
    entries = _fetch_all(q)

    # Group raw entries by line
    lines_entries: dict[str, list] = {}
    for e in entries:
        lid = e["line_id"]
        lines_entries.setdefault(lid, []).append(e)

    result = []
    for lid, elist in lines_entries.items():
        lname   = (elist[0].get("lines") or {}).get("name", "—")
        # Representative manpower: modal (most frequent) value for this line,
        # since the same crew works each hour — don't average or sum.
        from collections import Counter
        mp_counts = Counter(e["manpower"] for e in elist if (e.get("manpower") or 0) > 0)
        rep_mp    = mp_counts.most_common(1)[0][0] if mp_counts else 0

        result.append({
            "line_name":         lname,
            "manpower":          rep_mp,
            "output":            sum(e["output"] for e in elist),
            "units_per_man_day": _upmd_for_line(elist),  # mean of per-entry UPMDs
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
    td = to_date   or str(today)

    q = supabase_admin.table("production_entries").select(
        "date, output, target"
    ).gte("date", fd).lte("date", td).order("date")
    if line_id:
        q = q.eq("line_id", line_id)
    entries = _fetch_all(q)

    date_map: dict = {}
    for e in entries:
        d = e["date"]
        if d not in date_map:
            date_map[d] = {"date": d, "output": 0, "target": 0}
        date_map[d]["output"] += e["output"]
        date_map[d]["target"] += e["target"]

    return sorted(date_map.values(), key=lambda x: x["date"])



# ============================================================
# PERIOD BREAKDOWN TABLE  (daily / weekly / monthly rows)
# Returns rows of: label, target, output, gap, efficiency, manpower, upmd
# Used by the analytics dashboard breakdown table for all period types
# ============================================================
@router.get("/period-breakdown")
def get_period_breakdown(
    period: str = "daily",           # "daily" | "weekly" | "monthly"
    from_date: Optional[str] = None,
    to_date: Optional[str] = None,
    line_id: Optional[str] = None,
    line_ids: Optional[str] = None,
    user=Depends(get_current_user)
):
    from collections import defaultdict
    from datetime import datetime

    today = date.today()
    fd = from_date or str(today - timedelta(days=29))
    td = to_date   or str(today)

    q = supabase_admin.table("production_entries").select(
        "date, output, target, manpower, hours_worked, line_id, shift_id"
    ).gte("date", fd).lte("date", td)
    q = _apply_line_filter(q, line_id, line_ids)
    entries = _fetch_all(q)

    # Bucket function: maps an entry to its label
    def bucket(entry):
        d = entry["date"]           # "YYYY-MM-DD" string
        if period == "daily":
            dt = datetime.strptime(d, "%Y-%m-%d")
            return dt.strftime("%d %b")   # "01 Jan"
        elif period == "weekly":
            dt  = datetime.strptime(d, "%Y-%m-%d")
            day = dt.weekday()            # Mon=0 … Sun=6
            mon = dt - timedelta(days=day)
            sun = mon + timedelta(days=6)
            return f"W {mon.strftime('%d %b')}–{sun.strftime('%d %b')}"
        else:  # monthly
            dt = datetime.strptime(d, "%Y-%m-%d")
            return dt.strftime("%b %Y")   # "Jan 2026"

    # Sort key for ordering buckets
    def bucket_sort_key(entry):
        d = entry["date"]
        if period == "weekly":
            dt  = datetime.strptime(d, "%Y-%m-%d")
            day = dt.weekday()
            return (dt - timedelta(days=day)).strftime("%Y-%m-%d")
        elif period == "monthly":
            return entry["date"][:7]   # "YYYY-MM"
        return d

    # Group entries by bucket
    bucket_entries: dict = defaultdict(list)
    bucket_order:   dict = {}   # bucket_label -> sort key (first entry's key)
    for e in entries:
        label = bucket(e)
        bucket_entries[label].append(e)
        if label not in bucket_order:
            bucket_order[label] = bucket_sort_key(e)

    result = []
    for label in sorted(bucket_entries.keys(), key=lambda l: bucket_order[l]):
        elist    = bucket_entries[label]
        output   = sum(e["output"] for e in elist)
        target   = sum(e["target"] for e in elist)
        # _manpower_for_period sums crew sizes across all shift+line+day combinations
        manpower = _manpower_for_period(elist)
        upmd     = _upmd_for_line(elist)
        eff      = round(output / target * 100, 1) if target else 0.0
        result.append({
            "label":      label,
            "output":     output,
            "target":     target,
            "gap":        output - target,
            "efficiency": eff,
            "manpower":   manpower,
            "upmd":       upmd,
        })

    return result
@router.get("/monthly-summary")
def get_monthly_summary(
    year: Optional[int] = None,
    month: Optional[int] = None,
    user=Depends(get_current_user)
):
    today = date.today()
    y = year  or today.year
    m = month or today.month

    from_date = f"{y}-{m:02d}-01"
    to_date   = f"{y+1}-01-01" if m == 12 else f"{y}-{m+1:02d}-01"

    q_month = supabase_admin.table("production_entries").select(
        "date, output, target, manpower, hours_worked, line_id, model_id, "
        "lines(name), models(name)"
    ).gte("date", from_date).lt("date", to_date)
    entries = _fetch_all(q_month)

    # Group by line+model
    group_entries: dict[str, list] = {}
    group_meta: dict[str, dict] = {}
    for e in entries:
        key = f"{e['line_id']}::{e['model_id']}"
        group_entries.setdefault(key, []).append(e)
        if key not in group_meta:
            group_meta[key] = {
                "line_id":   e["line_id"],
                "model_id":  e["model_id"],
                "line_name": (e.get("lines")  or {}).get("name", "—"),
                "model_name":(e.get("models") or {}).get("name", "—"),
            }

    result = []
    for key, elist in group_entries.items():
        meta        = group_meta[key]
        total_out   = sum(e["output"] for e in elist)
        total_tgt   = sum(e["target"] for e in elist)
        eff         = round(total_out / total_tgt * 100, 1) if total_tgt else 0
        unique_days = len({e["date"] for e in elist})

        from collections import Counter
        mp_counts = Counter(e["manpower"] for e in elist if (e.get("manpower") or 0) > 0)
        rep_mp    = mp_counts.most_common(1)[0][0] if mp_counts else 0

        result.append({
            "line_id":           meta["line_id"],
            "model_id":          meta["model_id"],
            "line_name":         meta["line_name"],
            "model_name":        meta["model_name"],
            "days_recorded":     unique_days,
            "total_output":      total_out,
            "total_target":      total_tgt,
            "total_manpower":    rep_mp,
            "efficiency":        eff,
            "units_per_man_day": _upmd_for_line(elist),
        })

    return sorted(result, key=lambda x: (x["line_name"], x["model_name"]))


# ============================================================
# EFFICIENCY / PRODUCTIVITY
# ============================================================
@router.get("/efficiency")
def get_efficiency(
    period: str = "month",
    from_date: Optional[str] = None,
    to_date: Optional[str] = None,
    line_id: Optional[str] = None,
    line_ids: Optional[str] = None,
    shift_id: Optional[str] = None,
    user=Depends(get_current_user)
):
    if not from_date or not to_date:
        from_date, to_date = get_date_range(period)

    q = supabase_admin.table("production_entries").select(
        "output, target, manpower, line_id, lines(name)"
    ).gte("date", from_date).lte("date", to_date)
    q = _apply_line_filter(q, line_id, line_ids)
    if shift_id:
        q = q.eq("shift_id", shift_id)
    entries = _fetch_all(q)

    lines_entries: dict[str, list] = {}
    for e in entries:
        lines_entries.setdefault(e["line_id"], []).append(e)

    result = []
    for lid, elist in lines_entries.items():
        lname     = (elist[0].get("lines") or {}).get("name", "—")
        total_out = sum(e["output"] for e in elist)
        total_tgt = sum(e["target"] for e in elist)
        eff       = round(total_out / total_tgt * 100, 1) if total_tgt else 0
        result.append({
            "line_name":         lname,
            "efficiency":        eff,
            "units_per_man_day": _upmd_for_line(elist),
            "total_output":      total_out,
            "total_target":      total_tgt,
        })

    return sorted(result, key=lambda x: -x["efficiency"])
