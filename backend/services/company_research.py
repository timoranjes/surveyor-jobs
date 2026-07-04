"""
Company research service — multi-search strategy for deep, interview-ready profiles.
Strategy: 3 SerpApi calls per company (Glassdoor + news + projects), LLM synthesis.
Cost: ~$0.60 per company (3 searches). Cached 30 days.
"""

import os
import json
import asyncio
import httpx
from datetime import datetime, timedelta

_KEYS: list[str] = []
_key_index: int = 0


def _get_serpapi_key() -> str:
    """Round-robin SerpApi key with rate-limit awareness. Returns next key."""
    global _KEYS, _key_index
    if not _KEYS:
        keys_str = os.environ.get("SERPAPI_API_KEYS", "")
        if not keys_str:
            env_path = os.path.expanduser("~/.hermes/.env")
            if os.path.exists(env_path):
                with open(env_path) as f:
                    for line in f:
                        if line.startswith("SERPAPI_API_KEYS="):
                            keys_str = line.split("=", 1)[1].strip().strip('"').strip("'")
                            break
        if not keys_str:
            raise RuntimeError("SERPAPI_API_KEYS not found in env or ~/.hermes/.env")
        _KEYS = [k.strip() for k in keys_str.split(",") if k.strip()]
        if not _KEYS:
            raise RuntimeError("SERPAPI_API_KEYS is empty after parsing")
        _key_index = 0
    key = _KEYS[_key_index]
    _key_index = (_key_index + 1) % len(_KEYS)
    return key


async def _serpapi_search(query: str, num: int = 10, engine: str = "google", **extra_params) -> list[dict]:
    """Single SerpApi search. Returns list of organic results."""
    key = _get_serpapi_key()
    params = {
        "api_key": key,
        "engine": engine,
        "q": query,
        "num": num,
        "gl": "hk",
        "hl": "en",
        **extra_params,
    }
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.get("https://serpapi.com/search", params=params)
        resp.raise_for_status()
        data = resp.json()

    organic = data.get("organic_results", [])
    return [
        {
            "title": r.get("title", ""),
            "link": r.get("link", ""),
            "snippet": r.get("snippet", ""),
            "source": r.get("source", ""),
            "date": r.get("date", ""),
        }
        for r in organic
    ]


async def research_company(company_name: str, debug: bool = False) -> dict | tuple[dict, dict]:
    """
    Multi-search deep research on a company.
    Runs 3 searches in parallel, then LLM synthesizes all results.
    
    Returns structured dict with all research fields.
    """
    # ── Search 1: Glassdoor reviews ──
    glassdoor_query = f'{company_name} Glassdoor reviews rating Hong Kong'
    
    # ── Search 2: Recent news, projects, contract wins ──
    news_query = f'"{company_name}" Hong Kong contract OR project OR award OR expansion 2025 2026'
    
    # ── Search 3: HK government + public sector contracts ──
    gov_query = f'"{company_name}" Hong Kong government contract OR tender OR "development bureau" OR "housing authority" OR "highways department" OR "architectural services"'

    print(f"[Research] {company_name}: 3 parallel searches...")
    
    results = await asyncio.gather(
        _serpapi_search(glassdoor_query, num=8),
        _serpapi_search(news_query, num=8, tbs="qdr:y"),  # Past year
        _serpapi_search(gov_query, num=8),
        return_exceptions=True,
    )

    glassdoor_results = results[0] if not isinstance(results[0], Exception) else []
    news_results = results[1] if not isinstance(results[1], Exception) else []
    gov_results = results[2] if not isinstance(results[2], Exception) else []

    total_results = len(glassdoor_results) + len(news_results) + len(gov_results)
    print(f"[Research] {company_name}: {len(glassdoor_results)} glassdoor + {len(news_results)} news + {len(gov_results)} gov = {total_results} total")

    if total_results == 0:
        raise RuntimeError(f"No search results found for {company_name}")

    # ── LLM Synthesis ──
    result = await _synthesize(company_name, glassdoor_results, news_results, gov_results, debug=debug)

    if debug:
        data, debug_info = result
    else:
        data = result
        debug_info = None

    data["_serpapi_results_count"] = total_results
    data["_searched_at"] = datetime.utcnow().isoformat()
    data["_search_sources"] = {
        "glassdoor": len(glassdoor_results),
        "news": len(news_results),
        "government": len(gov_results),
    }

    if debug:
        debug_info["_serpapi_search_queries"] = {
            "glassdoor_query": glassdoor_query,
            "news_query": news_query,
            "gov_query": gov_query,
        }
        debug_info["_serpapi_results_count"] = total_results
        debug_info["_search_sources"] = data["_search_sources"]
        return data, debug_info

    return data


async def _synthesize(
    company_name: str,
    glassdoor_results: list[dict],
    news_results: list[dict],
    gov_results: list[dict],
    debug: bool = False,
) -> dict | tuple[dict, dict]:
    """Feed all search results to LLM for structured extraction."""
    from backend.services.llm import chat

    glassdoor_text = json.dumps(glassdoor_results, ensure_ascii=False)[:4000]
    news_text = json.dumps(news_results, ensure_ascii=False)[:4000]
    gov_text = json.dumps(gov_results, ensure_ascii=False)[:3000]

    prompt = f"""You are researching a Hong Kong surveying/construction company to help a fresh graduate prepare for job applications and interviews.

HK SURVEYING CONTEXT:
- HKIS APC is the primary professional pathway for HK surveyors. Look for mentions of "HKIS", "APC", "Graduate Training Scheme", "Scheme A training".
- RICS APC is also offered by international firms but HKIS is the dominant local qualification.
- Typical HK graduate surveyor salary (private sector): HK$20,000-28,000/month. Government Graduate Surveyor starts at MPS 19 (~HK$38,000/month).
- Cantonese proficiency is highly valued by HK employers.
- Major HK public sector clients: Development Bureau, Housing Authority, ArchSD, CEDD, HyD, LandsD, WSD, DSD, MTR, AAHK.

Company: {company_name}

=== GLASSDOOR SEARCH RESULTS ===
{glassdoor_text}

=== RECENT NEWS & PROJECTS ===
{news_text}

=== GOVERNMENT CONTRACTS ===
{gov_text}

CRITICAL RULES — VIOLATIONS WILL BE REJECTED:
1. ZERO FABRICATION: Every piece of information MUST be traceable to a search result above. If you can't find it, use "Unknown" (string), [] (empty array), or null (for numeric fields). Never invent.
2. HK PROJECTS GOLDEN RULE: hk_projects MUST ONLY contain projects explicitly mentioned in the search results above. If the search results show "Turner & Townsend won the Kai Tak Sports Park contract", you may ONLY include Kai Tak Sports Park — NOT "High West Site Development", "Central Waterfront", or any other project name you've seen in other contexts. Each project entry must have at least one specific search result hit that mentions that project by name + the company.
3. NO GENERIC TEMPLATES: Do not fill fields with plausible-sounding generic content (e.g., "MiC project in Hong Kong", "Government building project"). If no specific HK project is found, hk_projects MUST be an empty array [].
4. APPLY THE "WOULD THIS SURVIVE A FACT-CHECK?" TEST: Before writing anything, ask: can I point to which search result this comes from? If the answer is "no" — use Unknown/null/[].

Fields:
- overview: 4-5 sentence summary covering: what they do in HK, scale (staff/projects), main service lines, notable HK projects, reputation in surveying industry. Make this useful for interview preparation.
- employee_count: approximate HK staff if found (e.g. "200-500" or "500+"). "Unknown" if not found.
- founded_year: year founded if found. "Unknown" if not found.
- headquarters: HQ city/country (e.g. "Hong Kong", "London, UK"). "Unknown" if not found.
- glassdoor_rating: numeric rating out of 5. null if not found.
- glassdoor_review_count: total number of reviews. null if not found.
- glassdoor_pros: list of 3-5 real pros from employee reviews. Extract actual quotes/themes (e.g. "Good APC training support", "Flexible working hours"). Empty list [] if nothing found.
- glassdoor_cons: list of 3-5 real cons (e.g. "Long working hours during tender periods", "Slow promotion"). Empty list [] if nothing found.
- apc_training: boolean — do results indicate this firm provides HKIS/RICS APC training for surveyors? Check for mentions of "APC", "HKIS training", "RICS APC", "graduate scheme", "Scheme A".
- apc_training_details: if apc_training is true, describe what the training looks like (1-2 sentences). "Unknown" if not found.
- recent_news: list of 2-5 recent factual news items. Format: [{{"date": "2026-01", "title": "...", "detail": "..."}}]. Include contract wins, project awards, office expansions, leadership changes, new service lines.
- hk_government_contracts: list of HK government/statutory body contracts. Format: [{{"project": "...", "client": "...", "value": "...", "year": "..."}}]. Include Development Bureau, Housing Authority, Highways Dept, ArchSD, MTR, AAHK, etc.
- hk_projects: list of notable HK projects (not necessarily government). Format: [{{"name": "...", "type": "...", "description": "..."}}]. ⚠️ EACH entry must correspond to a project explicitly mentioned by name in the search results. NEVER include projects you know from general knowledge or other contexts. Empty array [] if none found in results.
- staff_turnover_notes: any indication of high/low turnover, layoffs, "always hiring", retention issues. "Unknown" if nothing found.
- interview_tips: 2-3 specific tips for interviewing at this company for a surveying role, based on Glassdoor reviews or company culture signals. Be specific — "Demonstrate knowledge of HKIS APC pathway" rather than "Be prepared". "Unknown" if insufficient data.
- competitor_comparison: how does this firm compare to main HK competitors in surveying? 2-3 sentences comparing size, specialization, reputation, career progression. "Unknown" if insufficient data.
- typical_graduate_salary: salary range for fresh graduate surveyors at this firm in HK$ if found. Use "Unknown" if not found — do NOT guess based on industry averages.
- graduate_program_details: if they have a graduate program, describe it (duration, rotations, mentorship). "Unknown" if not found.

Return ONLY valid JSON. No markdown, no explanation."""

    result = await chat(
        messages=[{"role": "user", "content": prompt}],
        temperature=0.2,
        max_tokens=3072,
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

    # ── Hallucination guard: validate hk_projects against search results ──
    _validate_projects(parsed, glassdoor_results, news_results, gov_results)

    if debug:
        debug_info["parsed_data"] = parsed
        return parsed, debug_info
    return parsed


def _validate_projects(parsed: dict, glassdoor: list, news: list, gov: list):
    """Strip hk_projects entries that aren't traceable to any search result."""
    projects = parsed.get("hk_projects")
    if not projects:
        return

    # Build a searchable text blob from all results
    all_text = ""
    for source_list in [glassdoor, news, gov]:
        for r in source_list:
            all_text += f"{r.get('title','')} {r.get('snippet','')} ".lower()

    valid = []
    for proj in projects:
        name = proj.get("name", "")
        if not name:
            continue
        # Project name must appear in at least one search result
        if name.lower() in all_text:
            valid.append(proj)
        else:
            print(f"[Anti-Hallucination] Stripped fabricated project: {name}")

    if len(valid) < len(projects):
        parsed["hk_projects"] = valid
        parsed["_hk_projects_filtered"] = True
        parsed["_hk_projects_removed"] = len(projects) - len(valid)
