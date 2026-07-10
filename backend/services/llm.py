"""
DeepSeek V4 Flash API client for CV matching and content generation.
Handles reasoning_content field behavior (sometimes content is empty for English prompts).
"""

import os
import json
import logging
import httpx

DEEPSEEK_API_KEY = None
DEEPSEEK_BASE = "https://api.deepseek.com/v1/chat/completions"


def _get_api_key() -> str:
    global DEEPSEEK_API_KEY
    if DEEPSEEK_API_KEY:
        return DEEPSEEK_API_KEY
    # Try environment first, then .env file
    key = os.environ.get("DEEPSEEK_API_KEY", "")
    if not key:
        env_path = os.path.expanduser("~/.hermes/.env")
        if os.path.exists(env_path):
            with open(env_path) as f:
                for line in f:
                    if line.startswith("DEEPSEEK_API_KEY="):
                        key = line.split("=", 1)[1].strip()
                        break
    if not key or len(key) < 20:
        raise RuntimeError("DEEPSEEK_API_KEY not found or appears redacted")
    DEEPSEEK_API_KEY = key
    return key


def _log_llm_call(messages, response_msg, temperature, json_mode):
    """Log LLM prompts and responses to a rotating debug log file."""
    import logging
    from datetime import datetime, timezone

    log_dir = os.environ.get("LLM_LOG_DIR") or os.path.join(
        os.path.dirname(os.path.dirname(__file__)), "logs"
    )
    os.makedirs(log_dir, exist_ok=True)
    log_path = os.path.join(log_dir, "llm_debug.log")

    logger = logging.getLogger("llm_debug")
    logger.setLevel(logging.DEBUG)
    # Prevent duplicate handlers
    if not logger.handlers:
        handler = logging.handlers.RotatingFileHandler(
            log_path, maxBytes=2 * 1024 * 1024, backupCount=5
        )
        handler.setFormatter(logging.Formatter(
            "%(asctime)s | %(message)s", datefmt="%Y-%m-%d %H:%M:%S"
        ))
        logger.addHandler(handler)

    prompt_preview = messages[0]["content"][:500] if messages else "(no messages)"
    response_preview = json.dumps(response_msg, ensure_ascii=False)[:1000]
    logger.debug(
        f"model=deepseek-chat | temp={temperature} | json_mode={json_mode} | "
        f"prompt={prompt_preview} | response={response_preview}"
    )


async def chat(
    messages: list[dict],
    temperature: float = 0.3,
    max_tokens: int = 4096,
    json_mode: bool = False,
    return_debug: bool = False,
) -> str | tuple[str, dict]:
    """
    Send chat completion to DeepSeek V4 Flash.
    Handles the reasoning_content fallback (model returns empty 'content'
    for some English prompts and puts output in 'reasoning_content').

    If return_debug=True, returns (content, debug_info) tuple where
    debug_info contains the raw prompt, raw response, model name, and timestamp.
    """
    from datetime import datetime, timezone

    key = _get_api_key()
    payload = {
        "model": "deepseek-chat",
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    if json_mode:
        payload["response_format"] = {"type": "json_object"}

    async with httpx.AsyncClient(timeout=90.0) as client:
        resp = await client.post(
            DEEPSEEK_BASE,
            headers={
                "Authorization": f"Bearer {key}",
                "Content-Type": "application/json",
            },
            json=payload,
        )
        resp.raise_for_status()
        data = resp.json()

    msg = data["choices"][0]["message"]
    content = msg.get("content", "") or ""
    if not content.strip():
        content = msg.get("reasoning_content", "") or ""

    if not content.strip():
        raise RuntimeError(f"DeepSeek returned empty response: {json.dumps(msg)[:500]}")

    # Always log LLM calls to a debug log file
    _log_llm_call(messages, msg, temperature, json_mode)

    if return_debug:
        debug_info = {
            "model": "deepseek-chat",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "prompt": messages[0]["content"] if messages else "",
            "raw_response": json.dumps(msg, ensure_ascii=False),
            "temperature": temperature,
            "max_tokens": max_tokens,
            "json_mode": json_mode,
        }
        return content, debug_info

    return content


async def analyze_cv(full_text: str, debug: bool = False) -> dict | tuple[dict, dict]:
    """Extract structured info from CV text — strict extraction, HK-context-aware, no fabrication."""
    prompt = f"""You are an AI assistant specialized in Hong Kong surveying/construction recruitment. Extract structured information from this CV.

HK SURVEYING CONTEXT (use for eligibility checks, do NOT fabricate if not in CV):
- HKIS (Hong Kong Institute of Surveyors) is the primary professional body. The APC (Assessment of Professional Competence) is the 2-year structured training pathway to become a Professional Surveyor (MHKIS).
- RICS (Royal Institution of Chartered Surveyors) also operates in HK but HKIS is the dominant local qualification. Many firms offer dual HKIS/RICS APC.
- HKIS-recognized surveying degrees (automatic graduate pathway entry): PolyU (BSc in Surveying — QS/BS/LS/GP/PD streams), HKU (BSc in Surveying), CityU (BSc in Surveying).
- HK surveying disciplines: QS (Quantity Surveying), BS (Building Surveying), LS (Land Surveying), GP (General Practice / Valuation), PD (Planning & Development).
- IVE/HKDI offer Higher Diplomas in surveying (not degree-level, not on HKIS graduate pathway, but accepted for technical roles).
- "Green Card" = Construction Industry Safety Card (mandatory for site work).
- Cantonese proficiency is critical for on-site communication, client liaison, and government work in HK.
- HK driving license (Class 1/2) is commonly listed as a job requirement.

CRITICAL EXTRACTION RULES:
1. ONLY extract what is EXPLICITLY stated in the CV — never invent, infer, or guess.
2. If a field is not mentioned, use null/[]/0 — NEVER fabricate data.
3. Skills must appear verbatim or be a clear synonym of something written (e.g. "MS Project" = "Microsoft Project").
4. Employer names must match EXACTLY what is written. If the CV says "Summer intern at AECOM", do NOT change it to "RLB".
5. Languages: only list languages the CV states the candidate speaks. Do NOT add languages not mentioned.
6. years_of_experience: count full-time years separately, internship months as fractions (e.g. 0.25 for 3-month internship). If there are multiple internships, sum them. Be explicit in your count — show your work.
7. hkis_eligible: true ONLY if the degree institution is PolyU, HKU, or CityU AND the degree is a surveying-related degree. This is automatic eligibility for the HKIS graduate pathway. Also true if HKIS membership or APC is explicitly mentioned. Otherwise false.
8. degree_relevance: map to one of "QS", "BS", "LS", "GP", "PD", "general_surveying", "construction_related", or "other".

Return a JSON object with:
- key_skills (list of strings extracted verbatim from the CV)
- education (list of objects with degree, institution, year)
- experience_summary (string: factual summary of what the CV actually says — no embellishment)
- years_of_experience (number: full-time years + internship months/12)
- certifications (list of strings from the CV)
- languages (list of strings EXPLICITLY mentioned in the CV)
- hkis_eligible (boolean: true if PolyU/HKU/CityU surveying degree, OR HKIS membership/APC explicitly stated)
- hkis_pathway_notes (string: explain WHY hkis_eligible is true/false, e.g. "PolyU BSc Surveying → automatic HKIS graduate pathway" or "Overseas degree, HKIS eligibility not determined from CV")
- institution_type (string: e.g. "PolyU", "HKU", "CityU", "IVE", "overseas", "other_hk" — from the degree institution)
- degree_relevance (string: "QS", "BS", "LS", "GP", "PD", "general_surveying", "construction_related", "other" — based on the degree title)
- has_cantonese (boolean: true if Cantonese/Chinese is mentioned as a language)
- has_green_card (boolean: true if Green Card or Construction Safety Card is mentioned)
- has_hk_driving_license (boolean: true if HK driving license is mentioned)

CV TEXT:
{full_text[:8000]}

Return ONLY valid JSON, no markdown formatting."""

    result = await chat(
        messages=[{"role": "user", "content": prompt}],
        temperature=0.2,
        max_tokens=2048,
        json_mode=True,
        return_debug=debug,
    )

    if debug:
        response, debug_info = result
    else:
        response = result
        debug_info = None

    # Clean potential markdown wrapping
    response = response.strip()
    if response.startswith("```"):
        response = response.split("\n", 1)[1].rsplit("\n```", 1)[0]

    parsed = json.loads(response)

    if debug:
        debug_info["parsed_data"] = parsed
        return parsed, debug_info
    return parsed


async def match_cv_to_job(cv_text: str, job_title: str, job_company: str, job_description: str, job_requirements: str, cv_analysis: dict, debug: bool = False) -> dict | tuple[dict, dict]:
    """Match CV against a specific job — honest weighted scoring with HK-specific criteria."""
    jd_full = f"{job_description}\n\nRequirements:\n{job_requirements}".strip()

    prompt = f"""You are an experienced Hong Kong surveying recruitment consultant at a specialist HK agency. Score this candidate's CV against a specific HK surveying/construction job posting.

HK RECRUITMENT CONTEXT (use for judging requirements; do NOT assume these if not in the CV/job):
- HKIS APC: The HKIS (Hong Kong Institute of Surveyors) APC is the standard 2-3 year structured training to become a Professional Surveyor (MHKIS). Many HK firms list "HKIS APC candidate" or "enrolled in HKIS APC" as required/preferred. PolyU, HKU, and CityU surveying graduates are automatically eligible for the HKIS graduate pathway.
- RICS APC: Also recognized in HK but less common than HKIS. Some international firms (e.g. JLL, CBRE, C&W) prefer RICS.
- Cantonese: Critical for most HK site-based roles. Client-facing QS/BS roles where liaison with local contractors/subcontractors is required → Cantonese is practically a hard requirement even if not explicitly stated. Corporate/regional roles may accept Mandarin + English only.
- HK salary reference (HKSAR government scales, 2024): Graduate Surveyor (MPS 19-27) ~HK$38,000-60,000/month; Technical Officer ~HK$24,000-44,000; Assistant Building Surveyor ~HK$40,000-65,000. Private sector graduate surveyor roles typically HK$20,000-28,000/month for fresh grads.
- Green Card (Construction Industry Safety Card): Mandatory for any role requiring site visits. If a job mentions site work and the CV lacks Green Card, that's a gap.
- MTR, AAHK, Development Bureau, Housing Authority, ArchSD, CEDD, LandsD, HyD, WSD, DSD are major HK public sector clients.

HARD REQUIREMENTS (must-have, 60% of total score):
- Degree discipline match: Is the candidate's degree the RIGHT surveying discipline for this role? QS degree for QS role, BS degree for BS role, LS degree for LS role. A wrong-discipline degree (e.g. BS applying for QS) is a severe gap.
- Language requirements: Does the job require Cantonese/Chinese? If yes and the CV doesn't mention Cantonese, that's a hard gap.
- Required certifications: Green Card, driving license, professional memberships explicitly listed as requirements.
- HKIS APC eligibility: If the job prefers/is for APC candidates, check if the candidate's degree qualifies.

SOFT REQUIREMENTS (nice-to-have, 40% of total score):
- Relevant internship/work experience in HK surveying/construction
- Software skills (AutoCAD, BIM/Revit, CostX, MicroStation, GIS, etc.)
- HKIS/RICS APC pathway awareness or enrollment
- HK project type exposure (residential, commercial, infrastructure, government)
- HK driving license (Class 1/2)

HONEST SCORING CALIBRATION — THIS IS CRITICAL:
- 0-29: Fundamentally wrong fit. Wrong discipline AND missing essential requirements. Do not apply.
- 30-49: Significant gaps. Missing a hard requirement (wrong discipline, no Cantonese when required, no Green Card for site roles). Long shot.
- 50-69: Partial match. Right discipline but missing experience or several soft skills. Worth applying but don't expect an interview.
- 70-84: Good match. Right discipline, meets most requirements, has some relevant experience/skills. Good chance of interview.
- 85-95: Strong match. Nearly all requirements met, relevant experience, right discipline, HK context-aware. High chance of interview.
- 96-100: Near-perfect match. Reserved for candidates who tick every box perfectly — extremely rare, almost never used.

Do NOT give every candidate 80-95%. A fresh graduate with a relevant degree but NO experience, NO Cantonese, NO Green Card should score around 50-65, NOT 80+. BE HONEST. Score inflation helps no one — it gives the candidate false confidence.

match_score: integer 0-100, calculated as (hard_score × 0.6) + (soft_score × 0.4).
In your internal reasoning, first score hard requirements 0-100, then soft 0-100, then compute the weighted total. Show your work in the explanations.

Return a JSON object with these EXACT fields:
- match_score: integer 0-100, honest weighted score
- hard_score: integer 0-100 (hard requirements sub-score, before weighting)
- soft_score: integer 0-100 (soft requirements sub-score, before weighting)
- hard_requirements_match: array of objects, each with fields: {{"requirement": string, "met": boolean, "explanation": string}}
- soft_requirements_match: array of objects, each with fields: {{"requirement": string, "level": "strong"|"partial"|"weak", "explanation": string}}
- strengths: list of 3-5 specific matching points, citing exact CV details — be PRECISE, do not fabricate
- gaps: list of 2-4 genuine missing requirements or weaknesses — only list things actually required by the job. Be specific: "No Green Card — required for site inspection duties" not just "No certifications"
- suggestions: list of 3-5 actionable CV improvements specifically for THIS job in the HK market (e.g. "Obtain Green Card before applying — mandatory for site work", "List Cantonese proficiency explicitly if you speak it")
- tailored_cv: rewrite the CV's professional summary for this specific job, ~150 words, using ONLY information actually present in the CV — do not invent experience
- interview_questions: list of 5 HK-specific interview questions for this role (see interview question guidelines below)

INTERVIEW QUESTION GUIDELINES — make them HK surveying specific:
Include a mix of:
1. A question about HKIS/RICS APC pathway knowledge
2. A technical question relevant to the discipline (QS: cost estimating/NRM; BS: Building Ordinance/inspection; LS: survey equipment/coordinates; GP: valuation methods/LandsD)
3. A question referencing the specific company's HK projects (if known from context)
4. A question about HK regulations/ordinances relevant to surveying
5. A behavioral question specific to HK site/office environment

Example QS questions: "How familiar are you with the HKIS APC requirements for the QS division?", "What do you know about the HK Standard Method of Measurement (SMM)?", "How would you handle a contractor disputing your measurement on site?"
Example BS questions: "What sections of the HK Building Ordinance are you familiar with?", "How would you conduct a building condition survey in an occupied HK public housing estate?"

JOB POSTING:
Title: {job_title}
Company: {job_company}
{jd_full}

CV ANALYSIS:
{json.dumps(cv_analysis, ensure_ascii=False)}

Return ONLY valid JSON, no markdown."""

    result = await chat(
        messages=[{"role": "user", "content": prompt}],
        temperature=0.2,
        max_tokens=4096,
        json_mode=True,
        return_debug=debug,
    )

    if debug:
        response, debug_info = result
    else:
        response = result
        debug_info = None

    response = response.strip()
    if response.startswith("```"):
        response = response.split("\n", 1)[1].rsplit("\n```", 1)[0]

    parsed = json.loads(response)

    if debug:
        debug_info["parsed_data"] = parsed
        return parsed, debug_info
    return parsed


async def generate_cover_letter(cv_text: str, job_title: str, job_company: str, job_description: str, cv_analysis: dict, debug: bool = False) -> str | tuple[str, dict]:
    """Generate a tailored cover letter with HK surveying context."""
    prompt = f"""Write a professional cover letter for a junior surveyor applying to this HK surveying/construction role. Use HK business English conventions (formal but not stiff, 250-350 words).

Include these elements naturally:
- Mention the candidate's HKIS APC eligibility (if applicable from CV) — e.g. "As a PolyU Surveying graduate, I am eligible for the HKIS APC graduate pathway..."
- Reference the company's HK projects or reputation (if known from the job description)
- Address any obvious gaps proactively: if Green Card is missing but required, say "I am prepared to obtain the Construction Industry Safety Card before commencing"
- Express understanding of the HK surveying profession — mention familiarity with HKIS, relevant HK ordinances, or HK-specific surveying practices if appropriate
- Do NOT fabricate experience, certifications, or skills not in the CV

CANDIDATE CV ANALYSIS:
{json.dumps(cv_analysis, ensure_ascii=False)[:1500]}

JOB: {job_title} at {job_company}
{job_description[:1500]}

Write the cover letter directly. No JSON wrapper, no subject line — start with "Dear Hiring Manager,"."""

    result = await chat(
        messages=[{"role": "user", "content": prompt}],
        temperature=0.3,
        max_tokens=2048,
        return_debug=debug,
    )

    if debug:
        response, debug_info = result
        debug_info["parsed_data"] = {"cover_letter": response}
        return response, debug_info
    return result


async def analyze_skill_gaps(cv_analysis: dict, all_job_requirements: list[dict], debug: bool = False) -> dict | tuple[dict, dict]:
    """Analyze skill gaps across all jobs — HK-context-aware recommendations."""
    jobs_json = json.dumps(all_job_requirements, ensure_ascii=False)[:4000]
    prompt = f"""Analyze this HK surveying candidate against ALL these job listings and return JSON:

HK TRAINING CONTEXT — when recommending courses/certifications, prefer these HK-specific options:
- Green Card (Construction Industry Safety Card) — CIC, 1-day course, ~HK$250. Essential for site work.
- HKIS APC enrollment — if the candidate has a recognized degree and hasn't started APC.
- BIM training: CIC-accredited BIM courses, HKIBIM professional membership pathway.
- Software: AutoCAD, Revit (BIM), CostX (QS), MicroStation (civil/infra), GIS (land surveying).
- HK driving license (Class 1/2) — often listed for roles requiring site visits.
- HKCAAVQ qualification assessment — for candidates with overseas degrees needing HK equivalency.
- Relevant HK short courses: HKU SPACE, PolyU SPEED, VTC PDC surveying-related modules.

Return JSON:
- missing_skills (list of objects, each with: "skill" (string), "jobs_requiring" (integer count), "priority" ("high"/"medium"/"low"), "common_in" (string: which discipline/role type typically needs this))
- recommended_courses (list of 3-5 specific HK courses/certifications to fill the biggest gaps, each with: "name", "provider", "why" (1 sentence), "estimated_cost_hkd" (number or null))
- overall_assessment (string: 2-3 sentence honest assessment of readiness for the HK surveying job market)

CV: {json.dumps(cv_analysis, ensure_ascii=False)[:1500]}
JOBS: {jobs_json}

Return ONLY valid JSON."""

    result = await chat(
        messages=[{"role": "user", "content": prompt}],
        temperature=0.3,
        max_tokens=2048,
        json_mode=True,
        return_debug=debug,
    )

    if debug:
        response, debug_info = result
    else:
        response = result
        debug_info = None

    response = response.strip()
    if response.startswith("```"):
        response = response.split("\n", 1)[1].rsplit("\n```", 1)[0]

    parsed = json.loads(response)

    if debug:
        debug_info["parsed_data"] = parsed
        return parsed, debug_info
    return parsed


async def research_company(company_name: str, debug: bool = False) -> dict | tuple[dict, dict]:
    """Research a company's HK surveying/construction presence (LLM-only fallback)."""
    prompt = f"""You are a Hong Kong surveying/construction industry analyst. Research this company's presence in HK for a fresh graduate preparing for interviews.

HK CONTEXT:
- Major HK surveying employers: AECOM, Arup, Arcadis, Atkins, C M Wong, Currie & Brown, Dragages, Gammon, Hip Hing, JLL, Langdon & Seah, Leighton, Paul Y., Rider Levett Bucknall (RLB), Savills, SEGRO, Sino Group, Sun Hung Kai Properties, Turner & Townsend, WSP.
- HK public sector clients: Development Bureau (DEVB), Housing Authority (HA), Architectural Services Department (ArchSD), Civil Engineering and Development Department (CEDD), Highways Department (HyD), Lands Department (LandsD), Water Supplies Department (WSD), Drainage Services Department (DSD), MTR Corporation, Airport Authority Hong Kong (AAHK).
- Graduate surveyor salaries in HK (private sector, 2024): HK$20,000-28,000/month for fresh grads at major consultancies. Government Graduate Surveyor starts at MPS 19 (~HK$38,000).
- HKIS APC: Most large firms offer structured HKIS/RICS APC training programs (typically called "Graduate Training Scheme" or "APC Programme"), lasting 2-3 years with rotations, mentorship, and CPD support.

Return JSON with these fields. Be FACTUAL — use "Unknown" or null for anything you cannot verify. Do NOT fabricate.

Fields:
- overview (2-3 sentence summary of the company and its HK operations relevant to surveyors)
- hk_projects (list of 2-4 notable HK projects relevant to surveyors, or [] if unknown. Include project name, type, and 1-sentence description)
- hk_government_contracts (list of known HK government/statutory body contracts. Format: [{{"project": "...", "client": "...", "year": "..."}}]. [] if unknown.)
- reputation_notes (brief note on reputation as employer for surveyors in HK — work culture, APC support, career progression. "Unknown" if not confident.)
- apc_training (boolean: is this firm known to offer HKIS/RICS APC training for surveyors?)
- apc_training_details (string: if apc_training is true, describe the program. "Unknown" if not found.)
- glassdoor_rating (number out of 5, or null if unknown)
- glassdoor_pros (list of 2-4 real themes from employee reviews, e.g. "Good APC training support". [] if unknown.)
- glassdoor_cons (list of 2-4 real themes, e.g. "Long hours during tender periods". [] if unknown.)
- typical_graduate_salary (string: salary range for fresh graduate surveyors in HK$ if known, e.g. "HK$22,000-26,000/month". "Unknown" if not found.)
- interview_tips (string: 2-3 specific tips for interviewing at this company for a surveying role. "Unknown" if insufficient data.)
- graduate_program_details (string: if they have a graduate program, describe it. "Unknown" if not found.)

Company: {company_name}
Return ONLY valid JSON."""

    result = await chat(
        messages=[{"role": "user", "content": prompt}],
        temperature=0.2,
        max_tokens=1536,
        json_mode=True,
        return_debug=debug,
    )

    if debug:
        response, debug_info = result
    else:
        response = result
        debug_info = None

    response = response.strip()
    if response.startswith("```"):
        response = response.split("\n", 1)[1].rsplit("\n```", 1)[0]

    parsed = json.loads(response)

    if debug:
        debug_info["parsed_data"] = parsed
        return parsed, debug_info
    return parsed
