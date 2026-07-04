"""Company research and salary benchmark routes — real data via SerpApi + LLM."""

import json
from datetime import datetime, timedelta
from fastapi import APIRouter, HTTPException
from backend.database import get_db
from backend.services.company_research import research_company as do_research

router = APIRouter(prefix="/api", tags=["companies"])

# Cache TTL: 30 days (companies don't change fast enough to warrant frequent re-searching)
CACHE_TTL_DAYS = 30


@router.get("/companies/{company_name}")
async def get_company(company_name: str, debug: bool = False):
    """Get company profile — from DB cache or freshly researched via SerpApi + LLM."""
    conn = get_db()

    # Check cached
    row = conn.execute(
        "SELECT * FROM company_profiles WHERE company_name = ?", (company_name,)
    ).fetchone()

    if row:
        row_dict = dict(row)
        last = row_dict.get("last_researched", "")
        if last:
            try:
                last_dt = datetime.fromisoformat(last)
                if datetime.utcnow() - last_dt < timedelta(days=CACHE_TTL_DAYS):
                    conn.close()
                    response = _format_response(row_dict)
                    if debug:
                        response["_debug"] = {"cached": True, "note": "Returned from cache (researched within 30 days). Use ?debug=true with a fresh company to see raw LLM output."}
                    return response
            except (ValueError, TypeError):
                pass  # Invalid date — re-research

    # Research fresh
    try:
        result = await do_research(company_name, debug=debug)
    except Exception as e:
        conn.close()
        raise HTTPException(status_code=502, detail=f"Company research failed: {e}")

    if debug:
        data, debug_info = result
    else:
        data = result

    # Serialize list/dict fields
    def _serialize(val):
        if val is None:
            return None
        if isinstance(val, (list, dict)):
            return json.dumps(val, ensure_ascii=False)
        return str(val)

    conn.execute(
        """INSERT OR REPLACE INTO company_profiles
           (company_name, overview, hk_projects, reputation_notes, glassdoor_rating,
            employee_count, founded_year, headquarters, recent_news,
            hk_government_contracts, glassdoor_review_count, glassdoor_pros,
            glassdoor_cons, apc_training, apc_training_details, staff_turnover_notes,
            interview_tips, competitor_comparison, typical_graduate_salary,
            graduate_program_details, last_researched)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (
            company_name,
            data.get("overview"),
            _serialize(data.get("hk_projects")),
            data.get("reputation_notes"),
            data.get("glassdoor_rating"),
            data.get("employee_count"),
            data.get("founded_year"),
            data.get("headquarters"),
            _serialize(data.get("recent_news")),
            _serialize(data.get("hk_government_contracts")),
            data.get("glassdoor_review_count"),
            _serialize(data.get("glassdoor_pros")),
            _serialize(data.get("glassdoor_cons")),
            1 if data.get("apc_training") else 0,
            data.get("apc_training_details"),
            data.get("staff_turnover_notes"),
            _serialize(data.get("interview_tips")),
            data.get("competitor_comparison"),
            data.get("typical_graduate_salary"),
            data.get("graduate_program_details"),
            datetime.utcnow().isoformat(),
        ),
    )
    conn.commit()

    # Fetch the freshly inserted row
    row = conn.execute(
        "SELECT * FROM company_profiles WHERE company_name = ?", (company_name,)
    ).fetchone()
    conn.close()

    response = _format_response(dict(row))

    if debug:
        response["_debug"] = debug_info

    return response


def _format_response(row: dict) -> dict:
    """Parse JSON fields back to native types for API response."""
    json_fields = [
        "recent_news", "hk_government_contracts", "hk_projects",
        "glassdoor_pros", "glassdoor_cons", "interview_tips",
    ]
    for field in json_fields:
        val = row.get(field)
        if isinstance(val, str):
            try:
                row[field] = json.loads(val)
            except (json.JSONDecodeError, TypeError):
                pass

    # Convert apc_training int back to bool
    if "apc_training" in row and isinstance(row["apc_training"], int):
        row["apc_training"] = bool(row["apc_training"])

    return row


@router.get("/salary-benchmarks")
def get_salary_benchmarks(discipline: str = None):
    """Get salary benchmarks by discipline and experience level."""
    conn = get_db()
    query = "SELECT * FROM salary_benchmarks"
    params = []
    if discipline:
        query += " WHERE discipline = ?"
        params.append(discipline)
    rows = conn.execute(query, params).fetchall()
    conn.close()
    return {"benchmarks": [dict(r) for r in rows]}
