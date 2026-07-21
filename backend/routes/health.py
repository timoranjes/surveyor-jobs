"""Operational health endpoints for job scraping."""

from fastapi import APIRouter
from backend.database import get_db

router = APIRouter(prefix="/api/health", tags=["health"])


@router.get("/scrape")
def scrape_health():
    """Return scrape health dashboard: last run, stale count, sources breakdown."""
    conn = get_db()
    counter_row = conn.execute(
        "SELECT counter FROM scrape_counter WHERE id = 1"
    ).fetchone()
    max_counter = int(counter_row[0]) if counter_row else 0
    cutoff = max_counter - 3

    # Find the last scrape run timestamp
    run_row = conn.execute(
        "SELECT ran_at FROM scrape_runs ORDER BY id DESC LIMIT 1"
    ).fetchone()
    if not run_row:
        # Fallback: use the most recent job updated_at
        run_row = conn.execute(
            "SELECT MAX(updated_at) AS ran_at FROM jobs"
        ).fetchone()

    total_jobs = conn.execute(
        "SELECT COUNT(*) FROM jobs WHERE is_active = 1"
    ).fetchone()[0]
    stale_jobs = conn.execute(
        """SELECT COUNT(*) FROM jobs
           WHERE is_active = 1 AND last_seen_scrape > 0 AND last_seen_scrape <= ?""",
        (cutoff,),
    ).fetchone()[0]
    sources = conn.execute(
        """SELECT COALESCE(source, 'unknown') AS name,
                  COUNT(*) AS count,
                  MAX(updated_at) AS last_seen
           FROM jobs
           WHERE is_active = 1
           GROUP BY COALESCE(source, 'unknown')
           ORDER BY count DESC, name""",
    ).fetchall()
    conn.close()

    return {
        "last_scrape_run": run_row["ran_at"] if run_row else None,
        "total_jobs": total_jobs,
        "stale_jobs": stale_jobs,
        "unique_sources": len(sources),
        "sources": [dict(row) for row in sources],
    }