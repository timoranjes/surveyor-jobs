"""Pipeline route — kanban view of applications grouped by pipeline stage."""

import json
from datetime import datetime, timedelta
from fastapi import APIRouter, HTTPException, Path
from pydantic import BaseModel
from typing import Optional
from backend.database import get_db

router = APIRouter(prefix="/api/pipeline", tags=["pipeline"])

STAGES = ["saved", "applied", "phone_screen", "interview", "assessment", "offer", "accepted", "rejected", "withdrawn"]
LEGACY_STATUSES = frozenset({"saved", "applied", "interview", "offer", "accepted", "rejected", "withdrawn"})


class PipelineStageUpdate(BaseModel):
    stage: str


def record_event(conn, application_id: int, event_type: str, from_status=None, to_status=None, note=None):
    """Insert a record into application_events."""
    conn.execute(
        "INSERT INTO application_events (application_id, event_type, from_status, to_status, note, created_at) "
        "VALUES (?, ?, ?, ?, ?, datetime('now'))",
        (application_id, event_type, from_status, to_status, note),
    )


@router.get("")
def get_pipeline():
    """Return all applications grouped by pipeline_stage (falling back to status)."""
    conn = get_db()
    rows = conn.execute("""
        SELECT a.id, a.job_id, a.notes, a.applied_date, a.pipeline_stage, a.status,
               a.pipeline_updated_at, a.created_at, a.follow_up_date,
               j.title AS job_title, j.company
        FROM applications a
        JOIN jobs j ON a.job_id = j.id
        ORDER BY a.pipeline_updated_at DESC, a.updated_at DESC
    """).fetchall()

    today = datetime.now()
    grouped = {s: [] for s in STAGES}

    for r in rows:
        rdict = dict(r)
        stage = rdict.get("pipeline_stage") or rdict.get("status") or "saved"

        # Calculate days_in_stage
        since_str = rdict.get("pipeline_updated_at") or rdict.get("created_at") or ""
        days_in_stage = None
        if since_str:
            try:
                since_dt = datetime.fromisoformat(since_str.replace("Z", "+00:00").replace(" ", "T"))
                days_in_stage = (today - since_dt).days
            except (ValueError, TypeError):
                pass

        if days_in_stage is None:
            days_in_stage = 0

        # Follow-up state
        follow_up_info = {}
        fud = rdict.get("follow_up_date")
        if fud:
            try:
                fud_dt = datetime.fromisoformat(fud.replace("Z", "+00:00").replace(" ", "T"))
                fut = fud_dt.date()
                t = today.date()
                follow_up_info["follow_up_date"] = fud
                follow_up_info["days_until_follow_up"] = (fut - t).days
                follow_up_info["is_overdue_follow_up"] = fut < t
            except (ValueError, TypeError):
                pass

        item = {
            "id": rdict["id"],
            "job_id": rdict["job_id"],
            "job_title": rdict["job_title"],
            "company": rdict["company"],
            "applied_date": rdict.get("applied_date"),
            "days_in_stage": days_in_stage,
            "notes": rdict.get("notes", "") or "",
            **follow_up_info,
        }
        if stage in grouped:
            grouped[stage].append(item)
        else:
            grouped["saved"].append(item)

    conn.close()

    stages_resp = []
    for s in STAGES:
        stages_resp.append({
            "stage": s,
            "count": len(grouped[s]),
            "items": grouped[s],
        })

    return {"stages": stages_resp}


@router.patch("/applications/{application_id}/pipeline")
def move_pipeline(application_id: int, update: PipelineStageUpdate):
    """Move an application to a different pipeline stage with safe status handling.
    Only writes to 'status' column if the target stage is a legacy status value;
    otherwise updates only pipeline_stage to avoid CHECK constraint failures.
    """
    if update.stage not in STAGES:
        raise HTTPException(status_code=400, detail=f"Invalid stage: {update.stage}. Must be one of: {', '.join(STAGES)}")

    conn = get_db()
    row = conn.execute("SELECT id, status, pipeline_stage FROM applications WHERE id = ?", (application_id,)).fetchone()
    if not row:
        conn.close()
        raise HTTPException(status_code=404, detail="Application not found")

    old_pipeline = row["pipeline_stage"] or row["status"] or "saved"
    new_stage = update.stage

    # Safe status write: only write to status if new_stage is a legacy status value
    if new_stage in LEGACY_STATUSES:
        conn.execute(
            """UPDATE applications
               SET pipeline_stage = ?, status = ?, pipeline_updated_at = datetime('now'),
                   updated_at = datetime('now')
               WHERE id = ?""",
            (new_stage, new_stage, application_id),
        )
    else:
        # phone_screen, assessment etc. — only update pipeline_stage, not status
        conn.execute(
            """UPDATE applications
               SET pipeline_stage = ?, pipeline_updated_at = datetime('now'),
                   updated_at = datetime('now')
               WHERE id = ?""",
            (new_stage, application_id),
        )

    # Record event if stage changed
    if new_stage != old_pipeline:
        record_event(conn, application_id, "status_changed",
                     from_status=old_pipeline, to_status=new_stage)

    conn.commit()

    updated = conn.execute("SELECT * FROM applications WHERE id = ?", (application_id,)).fetchone()
    conn.close()
    return dict(updated)


@router.get("/stats")
def pipeline_stats():
    """Return funnel metrics."""
    conn = get_db()
    rows = conn.execute("""
        SELECT a.pipeline_stage, a.status, a.pipeline_updated_at, a.created_at, a.applied_date
        FROM applications a
    """).fetchall()

    total = len(rows)

    stage_counts = {}
    for r in rows:
        stage = r["pipeline_stage"] or r["status"] or "saved"
        stage_counts[stage] = stage_counts.get(stage, 0) + 1

    def count(stage):
        return stage_counts.get(stage, 0)

    applied = count("applied") + count("saved")
    interview = count("interview") + count("phone_screen") + count("assessment")
    offer = count("offer") + count("accepted")

    def pct(numer, denom):
        if denom == 0:
            return 0
        return round(numer / denom * 100, 1)

    today = datetime.now()
    stage_days = {}
    stage_day_counts = {}
    for r in rows:
        stage = r["pipeline_stage"] or r["status"] or "saved"
        since_str = r["pipeline_updated_at"] or r["created_at"] or ""
        if since_str:
            try:
                since_dt = datetime.fromisoformat(since_str.replace("Z", "+00:00").replace(" ", "T"))
                days = (today - since_dt).days
                stage_days[stage] = stage_days.get(stage, 0) + days
                stage_day_counts[stage] = stage_day_counts.get(stage, 0) + 1
            except (ValueError, TypeError):
                pass

    avg_days = {}
    for s in STAGES:
        if stage_day_counts.get(s):
            avg_days[s] = round(stage_days[s] / stage_day_counts[s], 1)
        else:
            avg_days[s] = 0

    conn.close()

    return {
        "total_applications": total,
        "stage_counts": stage_counts,
        "conversion_rates": {
            "applied_to_interview": pct(interview, applied),
            "interview_to_offer": pct(offer, interview),
            "applied_to_offer": pct(offer, applied),
            "offer_acceptance": pct(count("accepted"), count("offer") + count("accepted")),
        },
        "average_days_in_stage": avg_days,
        "summary": {
            "total_applied": applied,
            "interviews_secured": interview,
            "offers_received": offer,
            "accepted": count("accepted"),
        },
    }