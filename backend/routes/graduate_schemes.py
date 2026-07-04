"""Graduate Schemes route — tracking HK surveying graduate programme deadlines."""

from datetime import datetime, date
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from typing import Optional
from backend.database import get_db

router = APIRouter(prefix="/api/graduate-schemes", tags=["graduate-schemes"])


class SchemeToggle(BaseModel):
    is_active: Optional[int] = None
    notes: Optional[str] = None


@router.get("")
def list_schemes(
    status: str = Query(None, description="open, upcoming, or closing_soon"),
    discipline: str = Query(None, description="Filter by discipline"),
):
    """List all graduate schemes, sorted by closing_date ascending."""
    conn = get_db()
    today = date.today().isoformat()

    query = "SELECT * FROM graduate_schemes WHERE 1=1"
    params = []

    if status == "open":
        query += " AND application_close >= ?"
        params.append(today)
    elif status == "upcoming":
        query += " AND application_open > ?"
        params.append(today)
    elif status == "closing_soon":
        # Within 30 days
        from datetime import timedelta
        soon = (date.today() + timedelta(days=30)).isoformat()
        query += " AND application_close >= ? AND application_close <= ?"
        params.append(today)
        params.append(soon)

    if discipline:
        query += " AND discipline = ?"
        params.append(discipline)

    query += " ORDER BY application_close ASC"

    rows = conn.execute(query, params).fetchall()

    schemes = []
    for r in rows:
        rd = dict(r)
        # Calculate days remaining
        days_remaining = None
        close_date = rd.get("application_close", "")
        if close_date and close_date != "TBC":
            try:
                close_dt = datetime.strptime(close_date, "%Y-%m-%d").date()
                days_remaining = (close_dt - date.today()).days
            except (ValueError, TypeError):
                pass
        rd["days_remaining"] = days_remaining
        schemes.append(rd)

    conn.close()
    return {"schemes": schemes}


@router.get("/stats")
def scheme_stats():
    """Return counts: open_now, closing_soon, upcoming, total."""
    conn = get_db()
    today = date.today().isoformat()
    from datetime import timedelta
    soon_dt = date.today() + timedelta(days=30)

    open_now = conn.execute(
        "SELECT COUNT(*) FROM graduate_schemes WHERE is_active = 1 AND application_close >= ? AND application_open <= ?",
        (today, today),
    ).fetchone()[0]

    closing_soon = conn.execute(
        "SELECT COUNT(*) FROM graduate_schemes WHERE is_active = 1 AND application_close >= ? AND application_close <= ?",
        (today, soon_dt.isoformat()),
    ).fetchone()[0]

    upcoming = conn.execute(
        "SELECT COUNT(*) FROM graduate_schemes WHERE is_active = 1 AND application_open > ?",
        (today,),
    ).fetchone()[0]

    total = conn.execute(
        "SELECT COUNT(*) FROM graduate_schemes WHERE is_active = 1",
    ).fetchone()[0]

    conn.close()

    return {
        "open_now": open_now,
        "closing_soon": closing_soon,
        "upcoming": upcoming,
        "total": total,
    }


@router.patch("/{scheme_id}")
def toggle_scheme(scheme_id: int, update: SchemeToggle):
    """Update scheme (toggle active, add notes)."""
    conn = get_db()
    row = conn.execute("SELECT id FROM graduate_schemes WHERE id = ?", (scheme_id,)).fetchone()
    if not row:
        conn.close()
        raise HTTPException(status_code=404, detail="Scheme not found")

    fields = []
    values = []
    if update.is_active is not None:
        fields.append("is_active = ?")
        values.append(update.is_active)
    if update.notes is not None:
        fields.append("notes = ?")
        values.append(update.notes)

    if fields:
        values.append(scheme_id)
        conn.execute(f"UPDATE graduate_schemes SET {', '.join(fields)} WHERE id = ?", values)
        conn.commit()

    updated = conn.execute("SELECT * FROM graduate_schemes WHERE id = ?", (scheme_id,)).fetchone()
    conn.close()
    return dict(updated)
