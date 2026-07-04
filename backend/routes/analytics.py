"""Analytics dashboard routes."""

from fastapi import APIRouter
from backend.database import get_db

router = APIRouter(prefix="/api/analytics", tags=["analytics"])


@router.get("")
def get_analytics():
    """Aggregate dashboard analytics."""
    conn = get_db()

    # Total active jobs
    total_jobs = conn.execute(
        "SELECT COUNT(*) FROM jobs WHERE is_active = 1 AND fresh_grad_friendly = 1"
    ).fetchone()[0]

    # By discipline
    by_discipline = {}
    rows = conn.execute(
        """SELECT discipline, COUNT(*) as cnt
           FROM jobs WHERE is_active = 1 AND fresh_grad_friendly = 1
           GROUP BY discipline"""
    ).fetchall()
    for r in rows:
        by_discipline[r["discipline"]] = r["cnt"]

    # Applications by status
    by_status = {}
    rows = conn.execute(
        "SELECT status, COUNT(*) as cnt FROM applications GROUP BY status"
    ).fetchall()
    for r in rows:
        by_status[r["status"]] = r["cnt"]

    # Response rate: of those who have advanced beyond "applied" (interview/offer/accepted)
    # as a percentage of those who applied
    total_applied = by_status.get("applied", 0) + by_status.get("saved", 0)
    advanced = sum(
        by_status.get(s, 0)
        for s in ["interview", "offer", "accepted"]
    )
    response_rate = round(advanced / max(total_applied, 1) * 100, 1)
    # Count applications by status for better detail
    total_applications = sum(by_status.values())

    # Average match score
    avg_row = conn.execute(
        "SELECT AVG(match_score) FROM cv_match_results"
    ).fetchone()
    avg_match_score = round(avg_row[0], 1) if avg_row[0] else 0

    # Salary benchmarks
    salary_rows = conn.execute("SELECT * FROM salary_benchmarks").fetchall()
    salary_benchmarks = [dict(r) for r in salary_rows]

    # Recent activity
    recent = conn.execute(
        """SELECT a.status, a.updated_at, j.title, j.company
           FROM applications a JOIN jobs j ON a.job_id = j.id
           ORDER BY a.updated_at DESC LIMIT 10"""
    ).fetchall()

    conn.close()

    return {
        "total_jobs": total_jobs,
        "by_discipline": by_discipline,
        "by_status": by_status,
        "response_rate": response_rate,
        "avg_match_score": avg_match_score,
        "salary_benchmarks": salary_benchmarks,
        "recent_activity": [dict(r) for r in recent],
    }
