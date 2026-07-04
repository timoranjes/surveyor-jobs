#!/usr/bin/env python3
"""
Google Jobs scraper via SerpApi — primary source for HK junior surveyor positions.
Aggregates listings from Indeed, LinkedIn, CTgoodjobs, JobsDB, company career pages.

Uses SerpApi's Google Jobs engine: https://serpapi.com/google-jobs-api
Free tier: 100 searches/month. $0.20/search after that.

Usage:
    # Set API key
    export SERPAPI_API_KEY="your_key"

    # Run standalone
    python3 scrapers/google_jobs_scraper.py

    # Or import
    from scrapers.google_jobs_scraper import scrape_google_jobs, run_full_scrape
"""

import os
import json
import time
import sqlite3
import hashlib
import re
from datetime import datetime
from urllib.parse import urlencode

import httpx

# Project root relative
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(PROJECT_ROOT, "data", "jobs.db")

# Load keys from ~/.hermes/.env
_KEYS: list[str] = []
_key_index: int = 0

def _load_keys():
    """Load SerpApi keys from env or .env file."""
    global _KEYS
    keys_str = os.environ.get("SERPAPI_API_KEYS", "")
    if not keys_str:
        env_file = os.path.expanduser("~/.hermes/.env")
        if os.path.exists(env_file):
            with open(env_file) as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith("#") and "=" in line:
                        k, v = line.split("=", 1)
                        if k == "SERPAPI_API_KEYS":
                            keys_str = v.strip().strip('"').strip("'")
                            break
    if keys_str:
        _KEYS = [k.strip() for k in keys_str.split(",") if k.strip()]

def _get_key() -> str:
    """Round-robin across keys."""
    global _key_index
    if not _KEYS:
        _load_keys()
    if not _KEYS:
        return ""
    key = _KEYS[_key_index]
    _key_index = (_key_index + 1) % len(_KEYS)
    return key

# Eager load on import
_load_keys()

SERPAPI_BASE = "https://serpapi.com/search"

# Search queries covering all four surveying disciplines
# Each: (query, discipline, location)
SEARCH_QUERIES = [
    # Quantity Surveying (largest category)
    ("graduate quantity surveyor Hong Kong", "quantity_surveying", "Hong Kong"),
    ("assistant quantity surveyor Hong Kong trainee", "quantity_surveying", "Hong Kong"),
    ("quantity surveying graduate program 2026 Hong Kong", "quantity_surveying", "Hong Kong"),
    # Building Surveying
    ("graduate building surveyor Hong Kong", "building_surveying", "Hong Kong"),
    ("assistant building surveyor Hong Kong entry level", "building_surveying", "Hong Kong"),
    # Land Surveying
    ("graduate land surveyor Hong Kong", "land_surveying", "Hong Kong"),
    ("assistant land surveyor Hong Kong geomatics", "land_surveying", "Hong Kong"),
    # General Practice / Planning
    ("graduate surveyor Hong Kong general practice", "general_practice", "Hong Kong"),
    ("surveyor trainee Hong Kong 2026", "other", "Hong Kong"),
    # Chinese-language queries (capture roles advertised in Chinese only)
    ("助理測量師", "other", "Hong Kong"),
    ("見習測量師", "other", "Hong Kong"),
    ("工料測量", "quantity_surveying", "Hong Kong"),
    ("土地測量", "land_surveying", "Hong Kong"),
    ("測量師學徒", "other", "Hong Kong"),
    ("建築測量", "building_surveying", "Hong Kong"),
    ("產業測量", "general_practice", "Hong Kong"),
]

# Keyword-based discipline classification
DISCIPLINE_KEYWORDS = {
    "quantity_surveying": [
        "quantity survey", "cost manager", "cost consultant", "qs ", "cost estimate",
        "commercial manager", "contracts manager", "contract administ",
        "bills of quantities", "boq", "tendering", "procurement construction",
    ],
    "land_surveying": [
        "land survey", "geomatics", "gis ", "geospatial", "cadastral",
        "topographic", "hydrographic", "lidar", "gnss", "gps survey",
        "boundary survey", "site survey",
    ],
    "building_surveying": [
        "building survey", "building inspection", "condition survey",
        "dilapidation", "building maintenance", "facade", "building pathology",
        "acm ", "asbestos", "unauthorised building", "ubw",
    ],
    "general_practice": [
        "general practice survey", "valuation survey", "property valuation",
        "estate survey", "land administration", "rating and valuation",
        "estate management", "property management", "lease management",
    ],
    "planning": [
        "planning survey", "town planning", "urban planning",
        "development survey", "planning application",
    ],
}

FRESH_GRAD_KEYWORDS = [
    "graduate", "trainee", "fresh grad", "fresh graduate", "entry level",
    "entry-level", "no experience", "0 year", "0 yr", "0-1", "scheme a",
    "graduate program", "graduate programme", "early career", "intern",
    "apprentice", "training", "2026 intake", "2026 graduate", "2026 fresh",
]

EXCLUDE_KEYWORDS = [
    # Only match when these appear as job-level descriptors, not in company boilerplate
    "senior surveyor", "senior quantity surveyor", "senior cost",
    "project manager", "contracts manager", "commercial manager",
    "5+ year", "5 years", "8 year", "8 years", "10 year", "10 years",
    "minimum 2 year", "minimum 3 year", "minimum 5 year",
    "min. 2 year", "min. 3 year", "min. 5 year",
    "post-qualification", "registered surveyor",
    "mrics", "mhkis", "chartered surveyor",
    "lead surveyor", "principal surveyor",
    "chief surveyor", "resident land surveyor", "resident quantity surveyor",
    "resident building surveyor",
]

NON_SURVEYING_KEYWORDS = [
    # Legal
    "solicitor", "paralegal", "legal counsel", "legal assistant",
    "legal secretary", "training contract", "law firm",
    # Finance / Trading
    "trader", "graduate trader", "equity", "investment banking",
    "wealth management", "financial analyst", "banking",
    "fund accountant", "hedge fund", "asset management",
    "insurance", "loss adjuster", "claims adjuster",
    # Management / Business
    "management trainee", "management associate",
    "business services", "business analyst",
    "graduate program", "graduate scheme", "graduate programme",
    "operations trainee", "operations management",
    "sourcing team", "procurement",
    "human resources", "hr trainee", "hr officer",
    # Engineering (unless title also has "surveyor" or "surveying")
    "civil engineer", "structural engineer", "traffic engineer",
    "rail engineer", "geotechnical engineer", "transport planner",
    "electrical engineer", "mechanical engineer",
    "graduate engineer", "assistant engineer", "engineer -",
    "engineering graduate", "engineering trainee",
    "scheme \"a\" engineer",
    "software engineer", "data scientist", "data engineer", "web developer",
    "frontend developer", "backend developer", "full stack", "devops", "machine learning",
    # Non-surveying graduate/trainee roles
    "property officer", "estate officer",
    "graduate intern", "sustainability intern",
    "town planner", "urban planner", "urban designer",
    "marketing manager", "sales manager",
    "marketing", "sales", "business development",
    "accountant", "audit", "tax",
    "registered nurse", "medical doctor", "school teacher", "head chef",
    # Company names
    "kpmg", "deloitte", "pwc", "ernst",
    "societe generale", "latham", "norton rose",
    "clyde & co", "kennedys", "mashreq",
    "charles taylor",
    # Misc
    "quality surveyor",  # common typo/spam
]

# Titles that are NEVER entry-level surveying jobs (checked before keyword matching)
NEVER_ENTRY_LEVEL_TITLES = [
    "chief surveyor", "resident land surveyor", "resident quantity surveyor",
    "resident building surveyor", "senior quantity surveyor", "senior surveyor",
    "principal surveyor", "lead surveyor", "director", "associate director",
    "commercial manager", "contracts manager", "project director",
]


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def make_external_id(title, company, source):
    raw = f"{title.lower().strip()}|{company.lower().strip()}|{source}"
    return hashlib.md5(raw.encode()).hexdigest()[:16]


def classify_discipline(title, description=""):
    """Auto-classify surveyor discipline from title + description."""
    text = (title + " " + description).lower()
    scores = {}
    for discipline, keywords in DISCIPLINE_KEYWORDS.items():
        scores[discipline] = sum(1 for kw in keywords if kw in text)
    best = max(scores, key=scores.get)
    return best if scores[best] > 0 else "other"


def is_surveying_job(title, description=""):
    """Check if the job is actually a surveying role. Non-surveying jobs return False."""
    title_lower = title.lower()
    text = (title + " " + description).lower()

    # Check non-surveying keywords
    for kw in NON_SURVEYING_KEYWORDS:
        if kw in title_lower:
            # Exception: allow through if the title clearly indicates surveying
            if ("engineer" in kw or "engineering" in kw or "scheme" in kw) and \
               ("surveyor" in title_lower or "surveying" in title_lower):
                continue
            # Exception: allow through if the title mentions a surveying role
            if "surveyor" in title_lower or "surveying" in title_lower:
                continue
            return False
        if kw in text:
            if ("engineer" in kw or "engineering" in kw or "scheme" in kw) and \
               ("surveyor" in title_lower or "surveying" in title_lower):
                continue
            if "surveyor" in title_lower or "surveying" in title_lower:
                continue
            return False

    # Must mention surveyor/surveying or quantity surveyor-adjacent terms
    surveyor_terms = ["surveyor", "surveying", "qs ", "quantity survey",
                       "cost manager", "cost consultant", "cost estimate",
                       "building inspect", "geomatics", "geospatial",
                       # Chinese surveying terms
                       "測量", "测量", "工料", "估价", "估價",
                       # Chinese "surveyor" variants (investigation/inspection — used in building surveyor context)
                       "建築調查", "建筑调查", "屋宇測量", "屋宇测量"]
    for term in surveyor_terms:
        if term in text:
            return True

    return False


def classify_experience_level(title, description=""):
    """Classify job into 3 tiers: graduate, entry, experienced."""
    text = (title + " " + description).lower()

    # Experienced first (most specific)
    for kw in EXCLUDE_KEYWORDS:
        if kw in text:
            return "experienced"

    # Graduate keywords
    for kw in FRESH_GRAD_KEYWORDS:
        if kw in text:
            return "graduate"

    # Entry keywords
    entry_kw = ["assistant", "trainee", "entry level", "entry-level",
                 "junior", "1 year", "2 year", "less experience",
                 "training provided", "willing to learn"]
    for kw in entry_kw:
        if kw in text:
            return "entry"

    return "entry"


def parse_posted_date(extensions):
    """Extract posted date from Google Jobs extensions array."""
    for ext in (extensions or []):
        if isinstance(ext, str) and ("ago" in ext or "day" in ext or "hour" in ext or "month" in ext):
            return ext
    return None


def parse_salary(description, snippet=""):
    """Try to extract salary range from description."""
    text = (description or "") + " " + (snippet or "")
    patterns = [
        r'HK?\$?\s*([\d,]+)\s*[-–—to]+\s*HK?\$?\s*([\d,]+)',
        r'\$([\d,]+)\s*[-–—]+\s*\$([\d,]+)',
        r'([\d,]+)\s*[-–—]+\s*([\d,]+)\s*(?:per month|/month|/m|monthly)',
    ]
    for p in patterns:
        m = re.search(p, text, re.IGNORECASE)
        if m:
            return f"HK${m.group(1).replace(',','')}-{m.group(2).replace(',','')}"
    return None


def insert_job(conn, job: dict):
    ext_id = make_external_id(job["title"], job["company"], job["source"])
    existing = conn.execute(
        "SELECT id FROM jobs WHERE external_id = ?", (ext_id,)
    ).fetchone()
    if existing:
        return None

    # Generate description_html from plain text
    from description_formatter import convert_description
    desc_html = ""
    if job.get("description"):
        try:
            desc_html = convert_description(job["description"])
        except Exception:
            pass

    # Classify experience level
    desc = job.get("description", "")
    exp_tier = classify_experience_level(job["title"], desc)

    # Extract closing date from description
    from scrapers.scraper import extract_closing_date
    closing_date = extract_closing_date(job.get("description", ""), job.get("requirements", ""))
    
    conn.execute(
        """INSERT INTO jobs
           (external_id, title, company, discipline, location, salary_range,
            description, description_html, requirements, url, source, posted_date,
            closing_date, fresh_grad_friendly, experience_level)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (
            ext_id, job["title"], job["company"], job["discipline"],
            job.get("location", "Hong Kong"), job.get("salary_range", ""),
            job.get("description", ""), desc_html,
            job.get("requirements", ""),
            job.get("url", ""), "google_jobs",
            job.get("posted_date", datetime.now().strftime("%Y-%m-%d")),
            closing_date,
            1 if exp_tier in ("graduate", "entry") else 0,
            exp_tier,
        ),
    )
    return conn.execute("SELECT last_insert_rowid()").fetchone()[0]


def search_google_jobs(query: str, location: str = "Hong Kong", discipline: str = "other") -> list[dict]:
    """Call SerpApi Google Jobs engine. Returns list of job dicts."""
    api_key = _get_key()
    if not api_key:
        print("    ⚠️  SERPAPI_API_KEYS not set — skipping Google Jobs")
        return []

    params = {
        "engine": "google_jobs",
        "q": query,
        "location": location,
        "hl": "en",
        "gl": "hk",
        "api_key": api_key,
    }

    jobs = []
    try:
        url = f"{SERPAPI_BASE}?{urlencode(params)}"
        resp = httpx.get(url, timeout=30)
        if resp.status_code != 200:
            print(f"    Google Jobs HTTP {resp.status_code}: {resp.text[:200]}")
            return jobs

        data = resp.json()

        if "error" in data:
            print(f"    Google Jobs API error: {data['error']}")
            return jobs

        job_results = data.get("jobs_results", [])
        print(f"    Google returned {len(job_results)} results for '{query}'")

        for jr in job_results:
            title = jr.get("title", "")
            company = jr.get("company_name", "Unknown")
            location = jr.get("location", "Hong Kong")
            description = jr.get("description", "")
            share_link = jr.get("share_link", "")
            via = jr.get("via", "")

            # Get apply link (prefer direct, fallback to Google share)
            apply_options = jr.get("apply_options", [])
            apply_link = share_link
            for opt in apply_options:
                if opt.get("link"):
                    apply_link = opt.get("link")
                    break

            # Extract posting date
            extensions = jr.get("extensions", [])
            if isinstance(extensions, list):
                posted_date = parse_posted_date(extensions)
            else:
                posted_date = None

            # Extract highlights + build a richer description for filtering
            highlights = jr.get("job_highlights", [])
            requirements = ""
            snippet_text = ""
            for h in highlights:
                if isinstance(h, dict):
                    if h.get("title") in ("Qualifications", "Requirements"):
                        items = h.get("items", [])
                        requirements = "\n".join(items[:5])
                    # Collect all highlight items as additional context
                    snippet_text += " " + " ".join(h.get("items", []))

            # Get salary
            salary_range = parse_salary(description, str(extensions))

            # Auto-classify discipline — use content-based classification
            # as primary (more accurate than search query discipline),
            # but keep the query's discipline if classification is ambiguous
            detected_discipline = classify_discipline(title, description)
            if detected_discipline == "other" and discipline != "other":
                detected_discipline = discipline

            # Non-surveying filter and experience level classification
            full_text = title + " " + description + " " + snippet_text
            if not is_surveying_job(title, full_text):
                continue

            # Don't filter by experience level at scrape time —
            # just classify and let the frontend filter
            exp_tier = classify_experience_level(title, full_text)

            jobs.append({
                "title": title.strip(),
                "company": company.strip(),
                "discipline": detected_discipline,
                "location": location,
                "salary_range": salary_range or "",
                "description": description[:2000] if description else "",
                "requirements": requirements[:1000] if requirements else "",
                "url": apply_link,
                "source": f"google_jobs_{via}" if via else "google_jobs",
                "posted_date": posted_date or datetime.now().strftime("%Y-%m-%d"),
                "fresh_grad_friendly": exp_tier in ("graduate", "entry"),
                "experience_level": exp_tier,
            })

    except Exception as e:
        print(f"    Google Jobs error: {e}")

    return jobs


def run_full_scrape() -> dict:
    """Main entry point: scrape all queries, insert into DB, return stats."""
    conn = get_db()

    # Increment scrape counter
    conn.execute("UPDATE scrape_counter SET counter = counter + 1")
    scrape_run = conn.execute("SELECT counter FROM scrape_counter").fetchone()[0]

    new_count = 0
    total_found = 0

    print(f"=== Google Jobs Scrape #{scrape_run}: {datetime.now().isoformat()} ===")

    for query, discipline, location in SEARCH_QUERIES:
        print(f"  Searching: '{query}' [{discipline}]")
        results = search_google_jobs(query, location, discipline)
        total_found += len(results)

        for job in results:
            rid = insert_job(conn, job)
            if rid:
                new_count += 1
                print(f"    NEW #{rid}: {job['title'][:60]} @ {job['company'][:30]} [{job['discipline']}]")

            # Mark job as seen in this scrape (whether new or existing)
            ext_id = make_external_id(job["title"], job["company"], job["source"])
            conn.execute(
                "UPDATE jobs SET last_seen_scrape = ? WHERE external_id = ?",
                (scrape_run, ext_id),
            )

        time.sleep(1.5)

    # ── Staleness pruning: deactivate jobs not seen for 3+ scrapes ──
    STALENESS_THRESHOLD = 3
    stale_cutoff = scrape_run - STALENESS_THRESHOLD
    stale_candidates = conn.execute("""
        SELECT j.id FROM jobs j
        WHERE j.is_active = 1
          AND j.last_seen_scrape > 0
          AND j.last_seen_scrape <= ?
          AND NOT EXISTS (SELECT 1 FROM applications a WHERE a.job_id = j.id)
    """, (stale_cutoff,)).fetchall()

    for row in stale_candidates:
        conn.execute("UPDATE jobs SET is_active = 0 WHERE id = ?", (row["id"],))
        print(f"    [PRUNE] Deactivated job #{row['id']} (not seen since scrape {stale_cutoff})")

    deactivated = len(stale_candidates)

    conn.commit()
    total_db = conn.execute("SELECT COUNT(*) FROM jobs WHERE is_active=1").fetchone()[0]
    conn.close()

    result = {
        "timestamp": datetime.now().isoformat(),
        "scrape_run": scrape_run,
        "total_found": total_found,
        "new_jobs": new_count,
        "deactivated_stale": deactivated,
        "total_in_db": total_db,
    }

    print(f"\nDone. Found {total_found}, added {new_count} new, pruned {deactivated} stale. DB total: {total_db}")
    return result


if __name__ == "__main__":
    result = run_full_scrape()
    print(json.dumps(result, indent=2))
