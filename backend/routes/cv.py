"""CV routes — upload, analyze, match, suggest, generate content."""

import asyncio
import json
from fastapi import APIRouter, HTTPException, UploadFile, File
from backend.database import get_db
from backend.models import CVUpload
from backend.services.llm import (
    analyze_cv,
    match_cv_to_job,
    generate_cover_letter,
    analyze_skill_gaps,
)
from backend.services.file_parser import extract_text

router = APIRouter(prefix="/api/cv", tags=["cv"])


@router.post("/upload")
def upload_cv(data: CVUpload):
    """Upload or update CV text."""
    conn = get_db()

    # Check existing
    existing = conn.execute("SELECT id FROM cv_data LIMIT 1").fetchone()
    if existing:
        conn.execute(
            "UPDATE cv_data SET full_text = ?, updated_at = datetime('now') WHERE id = ?",
            (data.full_text, existing["id"]),
        )
        cv_id = existing["id"]
    else:
        cursor = conn.execute(
            "INSERT INTO cv_data (full_text) VALUES (?)", (data.full_text,)
        )
        cv_id = cursor.lastrowid

    conn.commit()
    row = conn.execute("SELECT * FROM cv_data WHERE id = ?", (cv_id,)).fetchone()
    conn.close()
    return dict(row)


@router.post("/upload-file")
async def upload_cv_file(file: UploadFile = File(...)):
    """Upload CV as a file (PDF, DOCX, TXT). Extracts text automatically."""
    # Validate file type
    filename = file.filename or "cv.pdf"
    allowed = {".pdf", ".docx", ".doc", ".txt", ".md", ".rtf"}
    ext = filename.lower()[filename.rfind("."):] if "." in filename else ""
    if ext not in allowed:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type '{ext}'. Supported: PDF, DOCX, TXT",
        )

    # Read file
    file_bytes = await file.read()
    if not file_bytes:
        raise HTTPException(status_code=400, detail="Empty file uploaded")

    # Extract text
    try:
        full_text = extract_text(filename, file_bytes)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    if not full_text or len(full_text.strip()) < 50:
        raise HTTPException(
            status_code=400,
            detail="Extracted text is too short — the file may not contain a valid CV.",
        )

    # Save to DB (same logic as text upload)
    conn = get_db()
    existing = conn.execute("SELECT id FROM cv_data LIMIT 1").fetchone()
    if existing:
        conn.execute(
            "UPDATE cv_data SET full_text = ?, updated_at = datetime('now') WHERE id = ?",
            (full_text, existing["id"]),
        )
        cv_id = existing["id"]
    else:
        cursor = conn.execute(
            "INSERT INTO cv_data (full_text) VALUES (?)", (full_text,)
        )
        cv_id = cursor.lastrowid

    conn.commit()
    row = conn.execute("SELECT * FROM cv_data WHERE id = ?", (cv_id,)).fetchone()
    conn.close()

    return {
        "id": row["id"],
        "filename": filename,
        "text_length": len(full_text),
        "preview": full_text[:300] + ("..." if len(full_text) > 300 else ""),
    }


@router.get("")
def get_cv():
    """Get the stored CV."""
    conn = get_db()
    row = conn.execute("SELECT * FROM cv_data ORDER BY id DESC LIMIT 1").fetchone()
    conn.close()
    if not row:
        raise HTTPException(status_code=404, detail="No CV uploaded yet")
    return dict(row)


@router.post("/analyze")
async def analyze(debug: bool = False):
    """Run LLM analysis on the stored CV — extract skills, education, experience."""
    conn = get_db()
    row = conn.execute("SELECT * FROM cv_data ORDER BY id DESC LIMIT 1").fetchone()
    if not row:
        conn.close()
        raise HTTPException(status_code=404, detail="No CV uploaded yet")

    try:
        result = await analyze_cv(row["full_text"], debug=debug)

        if debug:
            analysis, debug_info = result
        else:
            analysis = result

        conn.execute(
            """UPDATE cv_data SET
               key_skills = ?, education = ?, experience_summary = ?,
               parsed_sections = ?, updated_at = datetime('now')
               WHERE id = ?""",
            (
                json.dumps(analysis.get("key_skills", [])),
                json.dumps(analysis.get("education", [])),
                analysis.get("experience_summary", ""),
                json.dumps(analysis, ensure_ascii=False),
                row["id"],
            ),
        )
        conn.commit()
    finally:
        conn.close()

    if debug:
        return {"analysis": analysis, "_debug": debug_info}
    return analysis


@router.post("/match/{job_id}")
async def match_to_job(job_id: int, debug: bool = False):
    """Match CV against a specific job — returns score, strengths, gaps, suggestions, tailored CV, cover letter, interview questions."""
    conn = get_db()
    cv_row = conn.execute("SELECT * FROM cv_data ORDER BY id DESC LIMIT 1").fetchone()
    job_row = conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()

    if not cv_row:
        conn.close()
        raise HTTPException(status_code=404, detail="No CV uploaded yet")
    if not job_row:
        conn.close()
        raise HTTPException(status_code=404, detail="Job not found")

    # Ensure CV is analyzed
    if not cv_row["parsed_sections"]:
        conn.close()
        raise HTTPException(
            status_code=400,
            detail="CV not analyzed yet — run POST /api/cv/analyze first",
        )

    cv_analysis = json.loads(cv_row["parsed_sections"])

    try:
        match_result = await match_cv_to_job(
            cv_text=cv_row["full_text"],
            job_title=job_row["title"],
            job_company=job_row["company"],
            job_description=job_row["description"] or "",
            job_requirements=job_row["requirements"] or "",
            cv_analysis=cv_analysis,
            debug=debug,
        )

        if debug:
            result, match_debug = match_result
        else:
            result = match_result
            match_debug = None

        cover_result = await generate_cover_letter(
            cv_text=cv_row["full_text"],
            job_title=job_row["title"],
            job_company=job_row["company"],
            job_description=job_row["description"] or "",
            cv_analysis=cv_analysis,
            debug=debug,
        )

        if debug:
            cover_letter, cover_debug = cover_result
        else:
            cover_letter = cover_result
            cover_debug = None

        # Upsert match result
        existing = conn.execute(
            "SELECT id FROM cv_match_results WHERE job_id = ? AND cv_id = ?",
            (job_id, cv_row["id"]),
        ).fetchone()

        if existing:
            conn.execute(
                """UPDATE cv_match_results SET
                   match_score = ?, strengths = ?, gaps = ?,
                   suggestions = ?, tailored_cv = ?, cover_letter = ?,
                   interview_questions = ?,
                   hard_requirements_match = ?, soft_requirements_match = ?
                   WHERE id = ?""",
                (
                    result.get("match_score"),
                    json.dumps(result.get("strengths", [])),
                    json.dumps(result.get("gaps", [])),
                    json.dumps(result.get("suggestions", [])),
                    result.get("tailored_cv"),
                    cover_letter,
                    json.dumps(result.get("interview_questions", [])),
                    json.dumps(result.get("hard_requirements_match", [])),
                    json.dumps(result.get("soft_requirements_match", [])),
                    existing["id"],
                ),
            )
        else:
            conn.execute(
                """INSERT INTO cv_match_results
                   (job_id, cv_id, match_score, strengths, gaps, suggestions,
                    tailored_cv, cover_letter, interview_questions,
                    hard_requirements_match, soft_requirements_match)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    job_id, cv_row["id"],
                    result.get("match_score"),
                    json.dumps(result.get("strengths", [])),
                    json.dumps(result.get("gaps", [])),
                    json.dumps(result.get("suggestions", [])),
                    result.get("tailored_cv"),
                    cover_letter,
                    json.dumps(result.get("interview_questions", [])),
                    json.dumps(result.get("hard_requirements_match", [])),
                    json.dumps(result.get("soft_requirements_match", [])),
                ),
            )
        conn.commit()
    finally:
        conn.close()

    response = {
        "job_id": job_id,
        "job_title": job_row["title"],
        "company": job_row["company"],
        "match_score": result.get("match_score"),
        "hard_requirements_match": result.get("hard_requirements_match", []),
        "soft_requirements_match": result.get("soft_requirements_match", []),
        "strengths": result.get("strengths", []),
        "gaps": result.get("gaps", []),
        "suggestions": result.get("suggestions", []),
        "tailored_cv": result.get("tailored_cv"),
        "cover_letter": cover_letter,
        "interview_questions": result.get("interview_questions", []),
    }

    if debug and match_debug:
        response["_debug"] = {
            "match": match_debug,
            "cover_letter": cover_debug,
        }

    return response


@router.post("/match-all")
async def match_all_jobs(debug: bool = False):
    """Match CV against ALL unmatched active jobs. Returns progress summary."""
    conn = get_db()
    cv_row = conn.execute("SELECT * FROM cv_data ORDER BY id DESC LIMIT 1").fetchone()
    if not cv_row:
        conn.close()
        raise HTTPException(status_code=404, detail="No CV uploaded yet")

    # Ensure CV is analyzed
    if not cv_row["parsed_sections"]:
        conn.close()
        raise HTTPException(
            status_code=400,
            detail="CV not analyzed yet — run POST /api/cv/analyze first",
        )

    cv_analysis = json.loads(cv_row["parsed_sections"])

    # Get all active entry/graduate jobs that don't have a match result yet
    unmatched = conn.execute("""
        SELECT j.id, j.title, j.company, j.description, j.requirements
        FROM jobs j
        LEFT JOIN cv_match_results m ON j.id = m.job_id AND m.cv_id = ?
        WHERE j.is_active = 1
          AND j.experience_level IN ('graduate', 'entry')
          AND m.id IS NULL
        ORDER BY j.posted_date DESC
    """, (cv_row["id"],)).fetchall()

    conn.close()

    if not unmatched:
        return {
            "matched": 0,
            "total": 0,
            "skipped": 0,
            "message": "All jobs already matched — nothing to do.",
            "results": [],
        }

    total = len(unmatched)
    
    # Use semaphore to limit concurrent DeepSeek calls (avoid rate limiting)
    semaphore = asyncio.Semaphore(4)
    
    async def match_one(job):
        """Match a single job, returning (result_dict, error_dict)."""
        async with semaphore:
            try:
                match_result = await match_cv_to_job(
                    cv_text=cv_row["full_text"],
                    job_title=job["title"],
                    job_company=job["company"],
                    job_description=job["description"] or "",
                    job_requirements=job["requirements"] or "",
                    cv_analysis=cv_analysis,
                    debug=False,
                )

                cover_letter = await generate_cover_letter(
                    cv_text=cv_row["full_text"],
                    job_title=job["title"],
                    job_company=job["company"],
                    job_description=job["description"] or "",
                    cv_analysis=cv_analysis,
                    debug=False,
                )

                # Upsert match result
                conn = get_db()
                existing = conn.execute(
                    "SELECT id FROM cv_match_results WHERE job_id = ? AND cv_id = ?",
                    (job["id"], cv_row["id"]),
                ).fetchone()

                if existing:
                    conn.execute("""
                        UPDATE cv_match_results SET
                            match_score = ?, strengths = ?, gaps = ?,
                            suggestions = ?, tailored_cv = ?, cover_letter = ?,
                            interview_questions = ?
                        WHERE id = ?
                    """, (
                        match_result.get("match_score"),
                        json.dumps(match_result.get("strengths", [])),
                        json.dumps(match_result.get("gaps", [])),
                        json.dumps(match_result.get("suggestions", [])),
                        match_result.get("tailored_cv"),
                        cover_letter,
                        json.dumps(match_result.get("interview_questions", [])),
                        existing["id"],
                    ))
                else:
                    conn.execute("""
                        INSERT INTO cv_match_results
                            (job_id, cv_id, match_score, strengths, gaps, suggestions,
                             tailored_cv, cover_letter, interview_questions)
                        VALUES (?,?,?,?,?,?,?,?,?)
                    """, (
                        job["id"], cv_row["id"],
                        match_result.get("match_score"),
                        json.dumps(match_result.get("strengths", [])),
                        json.dumps(match_result.get("gaps", [])),
                        json.dumps(match_result.get("suggestions", [])),
                        match_result.get("tailored_cv"),
                        cover_letter,
                        json.dumps(match_result.get("interview_questions", [])),
                    ))
                conn.commit()
                conn.close()

                return ({"job_id": job["id"], "title": job["title"],
                         "company": job["company"], "match_score": match_result.get("match_score")}, None)

            except Exception as e:
                return (None, {"job_id": job["id"], "title": job["title"], "error": str(e)})

    # Run all matches in parallel (4 concurrent)
    all_results = await asyncio.gather(*[match_one(job) for job in unmatched])
    
    results = [r for r, e in all_results if r is not None]
    errors = [e for r, e in all_results if e is not None]

    # Count total matched now
    conn = get_db()
    total_matched = conn.execute(
        "SELECT COUNT(*) FROM cv_match_results WHERE cv_id = ?", (cv_row["id"],)
    ).fetchone()[0]
    conn.close()

    return {
        "matched": len(results),
        "total": total,
        "skipped": len(errors),
        "total_matched_overall": total_matched,
        "message": f"Matched {len(results)} jobs" + (f", {len(errors)} failed" if errors else ""),
        "results": results,
        "errors": errors if errors else None,
    }
    
@router.post("/skill-gaps")
async def skill_gaps():
    """Analyze skill gaps across ALL jobs."""
    conn = get_db()
    cv_row = conn.execute("SELECT * FROM cv_data ORDER BY id DESC LIMIT 1").fetchone()
    if not cv_row or not cv_row["parsed_sections"]:
        conn.close()
        raise HTTPException(status_code=404, detail="CV not uploaded/analyzed")

    jobs = conn.execute(
        "SELECT title, company, requirements FROM jobs WHERE is_active = 1 AND fresh_grad_friendly = 1"
    ).fetchall()

    cv_analysis = json.loads(cv_row["parsed_sections"])
    job_reqs = [
        {"title": j["title"], "company": j["company"], "requirements": j["requirements"]}
        for j in jobs
    ]

    try:
        result = await analyze_skill_gaps(cv_analysis, job_reqs)

        # Store analysis
        existing = conn.execute(
            "SELECT id FROM skill_gap_analysis WHERE cv_id = ?", (cv_row["id"],)
        ).fetchone()
        if existing:
            conn.execute(
                "UPDATE skill_gap_analysis SET missing_skills = ?, recommended_courses = ? WHERE id = ?",
                (json.dumps(result), json.dumps(result.get("recommended_courses", [])), existing["id"]),
            )
        else:
            conn.execute(
                "INSERT INTO skill_gap_analysis (cv_id, missing_skills, recommended_courses) VALUES (?,?,?)",
                (cv_row["id"], json.dumps(result), json.dumps(result.get("recommended_courses", [])),
            ))
        conn.commit()
    finally:
        conn.close()

    return result
