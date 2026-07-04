"""Application tracking routes."""

from fastapi import APIRouter, HTTPException, Path
from backend.database import get_db
from backend.models import ApplicationUpdate

router = APIRouter(prefix="/api/applications", tags=["applications"])


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
    return {"applications": [dict(r) for r in rows]}


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
        "SELECT id FROM applications WHERE job_id = ?", (job_id,)
    ).fetchone()

    if existing:
        if update:
            fields = []
            values = []
            for k, v in update.dict(exclude_unset=True).items():
                fields.append(f"{k} = ?")
                values.append(v)
            # Also sync pipeline_stage if status is being set
            if "status" in update.dict(exclude_unset=True):
                if "pipeline_stage" not in update.dict(exclude_unset=True):
                    fields.append("pipeline_stage = ?")
                    values.append(update.status)
                if "pipeline_updated_at" not in update.dict(exclude_unset=True):
                    fields.append("pipeline_updated_at = datetime('now')")
            if fields:
                values.append(existing["id"])
                conn.execute(
                    f"UPDATE applications SET {', '.join(fields)}, updated_at = datetime('now') WHERE id = ?",
                    values,
                )
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
    fields = []
    values = []
    for k, v in update.dict(exclude_unset=True).items():
        fields.append(f"{k} = ?")
        values.append(v)
    # Sync pipeline_stage and pipeline_updated_at when status changes
    update_dict = update.dict(exclude_unset=True)
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
    conn.commit()
    row = conn.execute(
        "SELECT * FROM applications WHERE id = ?", (application_id,)
    ).fetchone()
    conn.close()
    if not row:
        raise HTTPException(status_code=404, detail="Application not found")
    return dict(row)
