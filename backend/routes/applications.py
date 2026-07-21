"""Application tracking routes with status timeline, follow-up API, and event recording."""

from datetime import datetime, date
from fastapi import APIRouter, HTTPException, Path, Query
from pydantic import BaseModel
from backend.database import get_db
from backend.models import ApplicationUpdate

router = APIRouter(prefix="/api/applications", tags=["applications"])

# Legacy status values that are safe to write into applications.status
LEGACY_STATUSES = frozenset({"saved", "applied", "interview", "offer", "accepted", "rejected", "withdrawn"})

# All pipeline stages (including non-status stages)
ALL_STAGES = ["saved", "applied", "phone_screen", "interview", "assessment", "offer", "accepted", "rejected", "withdrawn"]


def record_event(conn, application_id: int, event_type: str, from_status=None, to_status=None, note=None):
    """Insert a record into application_events."""
    conn.execute(
        "INSERT INTO application_events (application_id, event_type, from_status, to_status, note, created_at) "
        "VALUES (?, ?, ?, ?, ?, datetime('now'))",
        (application_id, event_type, from_status, to_status, note),
    )


def add_follow_up_fields(rdict: dict) -> dict:
    """Add computed follow-up fields to an application dict."""
    fud = rdict.get("follow_up_date")
    if fud:
        try:
            fud_dt = datetime.fromisoformat(fud.replace("Z", "+00:00").replace(" ", "T"))
            today = datetime.now()
            fut = fud_dt.date()
            t = today.date()
            rdict["days_until_follow_up"] = (fut - t).days
            rdict["is_overdue_follow_up"] = fut < t
        except (ValueError, TypeError):
            rdict["days_until_follow_up"] = None
            rdict["is_overdue_follow_up"] = False
    else:
        rdict["days_until_follow_up"] = None
        rdict["is_overdue_follow_up"] = False
    return rdict


# ── Fixed routes before parameterised routes ──

@router.get("/follow-ups")
def list_follow_ups(window: int = Query(30, ge=1, le=365)):
    """Return overdue + upcoming follow-ups within the given window (days)."""
    conn = get_db()
    today = date.today().isoformat()
    rows = conn.execute(
        """SELECT a.*, j.title as job_title, j.company as job_company,
                  j.discipline
           FROM applications a
           JOIN jobs j ON a.job_id = j.id
           WHERE a.follow_up_date IS NOT NULL
             AND a.follow_up_date != ''
           ORDER BY a.follow_up_date ASC
        """,
    ).fetchall()
    conn.close()

    results = []
    for r in rows:
        rdict = dict(r)
        fud = rdict.get("follow_up_date")
        if fud:
            try:
                fud_dt = datetime.fromisoformat(fud.replace("Z", "+00:00").replace(" ", "T"))
                fut = fud_dt.date()
                t = date.today()
                days = (fut - t).days
                if days <= window:  # overdue or upcoming within window
                    rdict["days_until_follow_up"] = days
                    rdict["is_overdue_follow_up"] = fut < t
                    results.append(rdict)
            except (ValueError, TypeError):
                pass

    return {"follow_ups": results, "total": len(results)}


@router.get("/{job_id}/timeline")
def get_application_timeline(job_id: int = Path(..., title="Job ID")):
    """Return status-change events for the application associated with a job."""
    conn = get_db()
    app = conn.execute(
        "SELECT id FROM applications WHERE job_id = ?", (job_id,)
    ).fetchone()
    if not app:
        conn.close()
        return {"events": []}
    rows = conn.execute(
        """SELECT id, application_id, event_type, from_status, to_status, note, created_at
           FROM application_events
           WHERE application_id = ?
           ORDER BY created_at ASC
        """,
        (app["id"],),
    ).fetchall()
    conn.close()
    return {"events": [dict(r) for r in rows]}


# ── Standard CRUD routes ──

@router.get("")
def list_applications(status: str = None):
    """List all applications with job details, optionally filtered by status."""
    conn = get_db()
    query = """
        SELECT a.*, j.title as job_title, j.company as job_company,
               j.discipline, j.location, j.url as job_url
        FROM applications a
        JOIN jobs j ON a.job_id = j.id
    """
    params = []
    if status:
        query += " WHERE a.status = ?"
        params.append(status)
    query += " ORDER BY a.updated_at DESC"

    rows = conn.execute(query, params).fetchall()
    conn.close()
    apps = [add_follow_up_fields(dict(r)) for r in rows]
    return {"applications": apps}


@router.post("/{job_id}")
def apply_to_job(job_id: int, update: ApplicationUpdate = None):
    """Create or update an application for a job."""
    conn = get_db()

    # Check job exists
    job = conn.execute("SELECT id FROM jobs WHERE id = ?", (job_id,)).fetchone()
    if not job:
        conn.close()
        raise HTTPException(status_code=404, detail="Job not found")

    # Upsert application
    existing = conn.execute(
        "SELECT id, status, pipeline_stage FROM applications WHERE job_id = ?", (job_id,)
    ).fetchone()

    if existing:
        if update:
            fields = []
            values = []
            old_status = existing["status"]
            update_dict = update.dict(exclude_unset=True)
            for k, v in update_dict.items():
                fields.append(f"{k} = ?")
                values.append(v)
            # Also sync pipeline_stage if status is being set
            if "status" in update_dict:
                if "pipeline_stage" not in update_dict:
                    fields.append("pipeline_stage = ?")
                    values.append(update.status)
                if "pipeline_updated_at" not in update_dict:
                    fields.append("pipeline_updated_at = datetime('now')")
            if fields:
                values.append(existing["id"])
                conn.execute(
                    f"UPDATE applications SET {', '.join(fields)}, updated_at = datetime('now') WHERE id = ?",
                    values,
                )
                # Record event if status changed
                if "status" in update_dict and update.status:
                    new_status = update.status
                    if new_status != old_status:
                        record_event(conn, existing["id"], "status_changed",
                                     from_status=old_status, to_status=new_status)
        conn.commit()
        row = conn.execute(
            "SELECT * FROM applications WHERE id = ?", (existing["id"],)
        ).fetchone()
    else:
        status = update.status if update and update.status else "saved"
        applied_date = update.applied_date if update else None
        notes = update.notes if update else None
        conn.execute(
            """INSERT INTO applications (job_id, status, applied_date, notes, pipeline_stage, pipeline_updated_at)
               VALUES (?, ?, ?, ?, ?, datetime('now'))""",
            (job_id, status, applied_date, notes, status),
        )
        conn.commit()
        row = conn.execute(
            "SELECT * FROM applications WHERE job_id = ?", (job_id,)
        ).fetchone()
        # Record created event
        record_event(conn, row["id"], "created", to_status=status)
        conn.commit()
        row = conn.execute(
            "SELECT * FROM applications WHERE id = ?", (row["id"],)
        ).fetchone()

    conn.close()
    return dict(row)


@router.delete("/{job_id}")
def delete_application(job_id: int = Path(..., title="Job ID to clear application for")):
    """Remove application record for a job (reset to unapplied)."""
    conn = get_db()
    conn.execute("DELETE FROM applications WHERE job_id = ?", (job_id,))
    conn.commit()
    conn.close()
    return {"ok": True}


@router.patch("/id/{application_id}")
def update_application(application_id: int, update: ApplicationUpdate):
    """Update application status or details by application ID."""
    conn = get_db()
    existing = conn.execute(
        "SELECT * FROM applications WHERE id = ?", (application_id,)
    ).fetchone()
    if not existing:
        conn.close()
        raise HTTPException(status_code=404, detail="Application not found")

    fields = []
    values = []
    old_status = existing["status"]
    old_pipeline = existing["pipeline_stage"] or old_status
    update_dict = update.dict(exclude_unset=True)
    for k, v in update_dict.items():
        fields.append(f"{k} = ?")
        values.append(v)
    # Sync pipeline_stage and pipeline_updated_at when status changes
    if "status" in update_dict:
        if "pipeline_stage" not in update_dict:
            fields.append("pipeline_stage = ?")
            values.append(update.status)
        if "pipeline_updated_at" not in update_dict:
            fields.append("pipeline_updated_at = datetime('now')")
    if not fields:
        conn.close()
        raise HTTPException(status_code=400, detail="No fields to update")

    values.append(application_id)
    conn.execute(
        f"UPDATE applications SET {', '.join(fields)}, updated_at = datetime('now') WHERE id = ?",
        values,
    )

    # Record event if status changed
    if "status" in update_dict and update.status:
        new_status = update.status
        if new_status != old_status:
            record_event(conn, application_id, "status_changed",
                         from_status=old_status, to_status=new_status)
    # Record event if pipeline_stage changed directly (without status change)
    if "pipeline_stage" in update_dict and update.pipeline_stage:
        new_pipeline = update.pipeline_stage
        if new_pipeline != old_pipeline and "status" not in update_dict:
            record_event(conn, application_id, "status_changed",
                         from_status=old_pipeline, to_status=new_pipeline)

    conn.commit()
    row = conn.execute(
        "SELECT * FROM applications WHERE id = ?", (application_id,)
    ).fetchone()
    conn.close()
    if not row:
        raise HTTPException(status_code=404, detail="Application not found")
    return dict(row)


class PipelineMove(BaseModel):
    stage: str


@router.patch("/{application_id}/pipeline")
def move_pipeline_via_applications(application_id: int, update: PipelineMove):
    """Move an application to a different pipeline stage, with safe status handling.
    Keeps 'status' within legacy CHECK constraint while allowing pipeline_stage
    to hold any stage value.
    """
    stage = update.stage
    if stage not in ALL_STAGES:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid stage: {stage}. Must be one of: {', '.join(ALL_STAGES)}",
        )

    conn = get_db()
    row = conn.execute(
        "SELECT id, status, pipeline_stage FROM applications WHERE id = ?",
        (application_id,),
    ).fetchone()
    if not row:
        conn.close()
        raise HTTPException(status_code=404, detail="Application not found")

    old_pipeline = row["pipeline_stage"] or row["status"] or "saved"

    # Safe status write: only write to status if new_stage is a legacy status value
    if stage in LEGACY_STATUSES:
        conn.execute(
            """UPDATE applications
               SET pipeline_stage = ?, status = ?, pipeline_updated_at = datetime('now'),
                   updated_at = datetime('now')
               WHERE id = ?""",
            (stage, stage, application_id),
        )
    else:
        # phone_screen, assessment etc. — only update pipeline_stage, not status
        conn.execute(
            """UPDATE applications
               SET pipeline_stage = ?, pipeline_updated_at = datetime('now'),
                   updated_at = datetime('now')
               WHERE id = ?""",
            (stage, application_id),
        )

    # Record event if stage changed
    if stage != old_pipeline:
        record_event(conn, application_id, "status_changed",
                     from_status=old_pipeline, to_status=stage)

    conn.commit()
    updated = conn.execute(
        "SELECT * FROM applications WHERE id = ?", (application_id,)
    ).fetchone()
    conn.close()
    return dict(updated)