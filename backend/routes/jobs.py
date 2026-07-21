"""Job listing routes — CRUD, search, filtering, and data quality."""

from datetime import datetime, date
import json

from fastapi import APIRouter, HTTPException, Query
from backend.database import get_db
from backend.models import JobCreate, JobResponse, JobFilter

router = APIRouter(prefix="/api/jobs", tags=["jobs"])


def _scrape_state(conn):
    """Return the current scrape counter and stale cutoff."""
    counter_row = conn.execute(
        "SELECT counter FROM scrape_counter WHERE id = 1"
    ).fetchone()
    counter = int(counter_row[0]) if counter_row else 0
    return counter, counter - 3


def _enrich_job(row, stale_cutoff):
    """Add computed data-quality fields to a job row. Additive only."""
    job = dict(row)
    last_seen = int(job.get("last_seen_scrape") or 0)
    job["stale"] = bool(last_seen > 0 and last_seen <= stale_cutoff)
    posted = job.get("posted_date")
    age_days = None
    if posted:
        try:
            posted_day = datetime.fromisoformat(str(posted).replace("Z", "+00:00")).date()
            age_days = max((date.today() - posted_day).days, 0)
        except (ValueError, TypeError, OverflowError):
            pass
    job["age_days"] = age_days
    job["has_closing_date"] = bool(job.get("closing_date"))
    job["has_description"] = bool(
        (job.get("description") or "").strip() or (job.get("description_html") or "").strip()
    )
    return job


def _enrich_rows(rows, stale_cutoff):
    return [_enrich_job(row, stale_cutoff) for row in rows]


@router.get("")
def list_jobs(
    discipline: str = Query(None),
    experience_level: str = Query("entry", description="graduate, entry, or all"),
    status: str = Query(None),
    search: str = Query(None),
    stale: bool = Query(None, description="Filter by computed stale status"),
    limit: int = Query(100, le=500),
    offset: int = Query(0),
):
    """List jobs with optional filters. Joins application status if available."""
    conn = get_db()
    _, stale_cutoff = _scrape_state(conn)
    query = """
        SELECT j.*, a.status as application_status
        FROM jobs j
        LEFT JOIN applications a ON j.id = a.job_id
        WHERE j.is_active = 1
    """
    params = []

    if discipline:
        query += " AND j.discipline = ?"
        params.append(discipline)
    if experience_level != "all":
        query += " AND j.experience_level = ?"
        params.append(experience_level)
    if status:
        query += " AND a.status = ?"
        params.append(status)
    if search:
        query += " AND (j.title LIKE ? OR j.company LIKE ? OR j.description LIKE ?)"
        s = f"%{search}%"
        params.extend([s, s, s])
    if stale is True:
        query += " AND j.last_seen_scrape > 0 AND j.last_seen_scrape <= ?"
        params.append(stale_cutoff)
    elif stale is False:
        query += " AND (j.last_seen_scrape = 0 OR j.last_seen_scrape > ?)"
        params.append(stale_cutoff)

    # Count
    count_query = query.replace(
        "SELECT j.*, a.status as application_status",
        "SELECT COUNT(*)",
    )
    total = conn.execute(count_query, params).fetchone()[0]

    query += " ORDER BY j.posted_date DESC LIMIT ? OFFSET ?"
    params.extend([limit, offset])

    rows = conn.execute(query, params).fetchall()
    conn.close()

    return {
        "total": total,
        "jobs": _enrich_rows(rows, stale_cutoff),
    }


@router.get("/ranked")
def ranked_jobs():
    """Return all active entry/graduate jobs sorted by match_score descending."""
    conn = get_db()
    _, stale_cutoff = _scrape_state(conn)
    rows = conn.execute("""
        SELECT j.id AS job_id, j.title, j.company, j.discipline, j.location,
               j.salary_range, j.posted_date, j.experience_level,
               m.match_score, m.strengths, m.gaps,
               CASE WHEN m.match_score IS NOT NULL THEN 1 ELSE 0 END AS has_match
        FROM jobs j
        LEFT JOIN cv_match_results m ON j.id = m.job_id
        WHERE j.is_active = 1 AND j.experience_level IN ('graduate', 'entry')
        ORDER BY m.match_score DESC, j.posted_date DESC
    """).fetchall()

    results = []
    for r in rows:
        rd = dict(r)
        strengths = rd.get("strengths")
        if isinstance(strengths, str):
            try:
                strengths = json.loads(strengths)
            except Exception:
                strengths = [strengths]
        gaps = rd.get("gaps")
        if isinstance(gaps, str):
            try:
                gaps = json.loads(gaps)
            except Exception:
                gaps = [gaps]

        match_score = rd.get("match_score")
        if match_score is not None:
            match_score = round(float(match_score), 1)
        else:
            match_score = 0

        # Compute extra fields
        last_seen = int(rd.get("last_seen_scrape") or 0)
        stale = bool(last_seen > 0 and last_seen <= stale_cutoff)
        posted = rd.get("posted_date")
        age_days = None
        if posted:
            try:
                posted_day = datetime.fromisoformat(str(posted).replace("Z", "+00:00")).date()
                age_days = max((date.today() - posted_day).days, 0)
            except (ValueError, TypeError, OverflowError):
                pass

        results.append({
            "job_id": rd["job_id"],
            "title": rd["title"],
            "company": rd["company"],
            "discipline": rd["discipline"],
            "location": rd.get("location"),
            "salary_range": rd.get("salary_range"),
            "posted_date": rd.get("posted_date"),
            "experience_level": rd.get("experience_level"),
            "match_score": match_score,
            "strengths": (strengths if isinstance(strengths, list) else [])[:3],
            "gaps": (gaps if isinstance(gaps, list) else [])[:3],
            "has_match": bool(rd["has_match"]),
            "stale": stale,
            "age_days": age_days,
            "has_closing_date": bool(rd.get("closing_date")),
            "has_description": bool(
                (rd.get("description") or "").strip() or (rd.get("description_html") or "").strip()
            ),
        })

    conn.close()
    return {"jobs": results}


@router.get("/{job_id}")
def get_job(job_id: int):
    """Get a single job with application status and match data."""
    conn = get_db()
    _, stale_cutoff = _scrape_state(conn)
    row = conn.execute(
        """SELECT j.*, a.status as application_status, a.id as application_id,
                  m.match_score, m.strengths, m.gaps, m.suggestions,
                  m.tailored_cv, m.cover_letter, m.interview_questions
           FROM jobs j
           LEFT JOIN applications a ON j.id = a.job_id
           LEFT JOIN cv_match_results m ON j.id = m.job_id
           WHERE j.id = ?""",
        (job_id,),
    ).fetchone()
    conn.close()
    if not row:
        raise HTTPException(status_code=404, detail="Job not found")
    return _enrich_job(row, stale_cutoff)


@router.post("/scrape")
def trigger_scrape():
    """Trigger a scraping run (primary: Google Jobs, fallback: LinkedIn)."""
    import subprocess, sys, os
    scraper_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
        "scrapers", "scraper.py"
    )
    try:
        result = subprocess.run(
            [sys.executable, scraper_path, "--skip-backfill"],
            capture_output=True, text=True, timeout=300, cwd=os.path.dirname(scraper_path),
        )
        return {"ok": True, "stdout": result.stdout[-3000:], "stderr": result.stderr[-1000:]}
    except subprocess.TimeoutExpired:
        return {"ok": False, "error": "Scrape timed out after 5 minutes"}
    except Exception as e:
        return {"ok": False, "error": str(e)}


@router.post("/dedup")
def deduplicate_jobs():
    """Soft-delete duplicate active listings by normalized title + company.

    Idempotent — safe to run multiple times. Keeps the row with the longest
    description (or highest id if tied). Does not interfere with the scraper's
    own last_seen_scrape pruning logic.
    """
    conn = get_db()
    groups = conn.execute("""
        SELECT LOWER(title) AS normalized_title,
               LOWER(company) AS normalized_company,
               COUNT(*) AS duplicate_count
        FROM jobs
        WHERE is_active = 1
        GROUP BY LOWER(title), LOWER(company)
        HAVING COUNT(*) > 1
    """).fetchall()

    deduped = 0
    kept = 0
    details = []
    for group in groups:
        rows = conn.execute("""
            SELECT id, title, company, description,
                   LENGTH(COALESCE(description, '')) AS description_length
            FROM jobs
            WHERE is_active = 1 AND LOWER(title) = ? AND LOWER(company) = ?
            ORDER BY description_length DESC, id DESC
        """, (group["normalized_title"], group["normalized_company"])).fetchall()
        keeper = rows[0]
        duplicate_ids = [row["id"] for row in rows[1:]]
        if duplicate_ids:
            conn.executemany(
                "UPDATE jobs SET is_active = 0 WHERE id = ?",
                [(job_id,) for job_id in duplicate_ids],
            )
            deduped += len(duplicate_ids)
            kept += 1
            details.append({
                "title": keeper["title"],
                "company": keeper["company"],
                "kept_id": keeper["id"],
                "duplicate_ids": duplicate_ids,
            })

    conn.commit()
    conn.close()
    return {"deduped": deduped, "kept": kept, "details": details}


@router.post("/refresh-stale")
def refresh_stale_jobs():
    """Return the current computed stale count without adding a DB column."""
    conn = get_db()
    max_counter, stale_cutoff = _scrape_state(conn)
    stale_count = conn.execute("""
        SELECT COUNT(*) FROM jobs
        WHERE is_active = 1 AND last_seen_scrape > 0 AND last_seen_scrape <= ?
    """, (stale_cutoff,)).fetchone()[0]
    conn.close()
    return {
        "stale": stale_count,
        "stale_jobs": stale_count,
        "max_scrape_counter": max_counter,
        "cutoff": stale_cutoff,
    }


@router.post("")
def create_job(job: JobCreate):
    """Add a job listing (used by scrapers)."""
    conn = get_db()
    try:
        cursor = conn.execute(
            """INSERT INTO jobs (title, company, discipline, location, salary_range,
               description, requirements, url, source, posted_date, closing_date,
               fresh_grad_friendly, experience_level)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                job.title, job.company, job.discipline, job.location,
                job.salary_range, job.description, job.requirements,
                job.url, job.source, job.posted_date, job.closing_date,
                1 if job.fresh_grad_friendly else 0, job.experience_level,
            ),
        )
        conn.commit()
        job_id = cursor.lastrowid
        row = conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
        conn.close()
        return dict(row)
    except Exception as e:
        conn.close()
        if "UNIQUE constraint" in str(e):
            raise HTTPException(status_code=409, detail="Job already exists")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/{job_id}")
def delete_job(job_id: int):
    """Soft-delete a job."""
    conn = get_db()
    conn.execute("UPDATE jobs SET is_active = 0 WHERE id = ?", (job_id,))
    conn.commit()
    conn.close()
    return {"ok": True}