#!/usr/bin/env python3
"""
Job board scraper for HK junior surveyor positions.
Primary source: Google Jobs via SerpApi (aggregates Indeed, LinkedIn, CTgoodjobs, JobsDB, company sites).
Fallback: LinkedIn search pages (limited).
Indeed/CTgoodjobs are blocked by anti-bot — not scrapeable directly.
Runs as cron job. Deduplicates by external_id.
"""

import sys
import os
import json
import time
import sqlite3
import hashlib
import re
import html
from datetime import datetime
from urllib.parse import quote, urljoin

import httpx
from bs4 import BeautifulSoup

# Import Google Jobs scraper
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from scrapers.google_jobs_scraper import search_google_jobs, SEARCH_QUERIES as GOOGLE_QUERIES
from scrapers.backfill_descriptions import backfill_all

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "jobs.db")

SEARCH_CONFIGS = [
    # (platform, search_url, discipline)
    # CTgoodjobs — server-side rendered, best target
    ("ctgoodjobs", "https://jobs.ctgoodjobs.hk/jobs/graduate-quantity-surveyor-jobs", "quantity_surveying"),
    ("ctgoodjobs", "https://jobs.ctgoodjobs.hk/jobs/graduate-surveyor-jobs", "building_surveying"),
    ("ctgoodjobs", "https://jobs.ctgoodjobs.hk/jobs/land-surveyor-jobs", "land_surveying"),
    ("ctgoodjobs", "https://jobs.ctgoodjobs.hk/jobs/quantity-surveyor-trainee-jobs", "quantity_surveying"),
    ("ctgoodjobs", "https://jobs.ctgoodjobs.hk/jobs/assistant-quantity-surveyor-jobs", "quantity_surveying"),
    ("ctgoodjobs", "https://jobs.ctgoodjobs.hk/jobs/assistant-surveyor-jobs", "building_surveying"),
    # Indeed — will try but likely blocked; search links at minimum
    ("indeed", "https://hk.indeed.com/jobs?q=graduate+quantity+surveyor&l=Hong+Kong&sc=0kf%3Ajt(graduate)%3B", "quantity_surveying"),
    ("indeed", "https://hk.indeed.com/jobs?q=graduate+land+surveyor&l=Hong+Kong&sc=0kf%3Ajt(graduate)%3B", "land_surveying"),
    ("indeed", "https://hk.indeed.com/jobs?q=graduate+building+surveyor&l=Hong+Kong&sc=0kf%3Ajt(graduate)%3B", "building_surveying"),
    ("indeed", "https://hk.indeed.com/jobs?q=assistant+quantity+surveyor&l=Hong+Kong&sc=0kf%3Ajt(entry_level)%3B", "quantity_surveying"),
    ("indeed", "https://hk.indeed.com/jobs?q=assistant+land+surveyor&l=Hong+Kong&sc=0kf%3Ajt(entry_level)%3B", "land_surveying"),
    # LinkedIn — search pages only (job details behind auth wall)
    ("linkedin", "https://hk.linkedin.com/jobs/graduate-quantity-surveyor-jobs", "quantity_surveying"),
    ("linkedin", "https://hk.linkedin.com/jobs/graduate-surveyor-jobs", "other"),
    ("linkedin", "https://hk.linkedin.com/jobs/land-surveyor-jobs", "land_surveying"),
]

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)

# ── Experience Level Classification ──
# Three tiers: "graduate" (Scheme A, APC, 0 years, graduate program),
#               "entry" (0-2 years, assistant, trainee, "less experience considered"),
#               "experienced" (3+ years, senior, manager)

GRADUATE_KEYWORDS = [
    "scheme a", "apc programme", "apc program", "graduate programme",
    "graduate program", "graduate trainee", "graduate surveyor",
    "2026 intake", "2026 graduate", "2026 fresh", "fresh graduate",
    "no experience", "0 year", "0 yr", "0 yr.", "fresh grad",
]

ENTRY_KEYWORDS = [
    "assistant", "trainee", "entry level", "entry-level",
    "0-1", "1 year", "1 yr", "1-2", "2 year", "2 yr",
    "less experience", "junior", "early career",
    "willing to learn", "training provided",
]

EXPERIENCED_KEYWORDS = [
    "senior", "manager", "director", "principal", "lead",
    "3+ year", "3 year", "4 year", "5 year", "5+ year",
    "8 year", "10 year", "experienced",
    "minimum 3 year", "minimum 5 year",
    "min. 3 year", "min. 5 year",
    "post-qualification", "registered surveyor",
    "chief surveyor", "resident land surveyor", "resident quantity surveyor",
    "mrics", "mhkis", "chartered surveyor",
]

# ── Non-Surveying Job Blacklist ──
# Jobs matching ANY of these are NOT surveying roles. Excluded entirely.
NON_SURVEYING_KEYWORDS = [
    # Legal
    "solicitor", "paralegal", "legal counsel", "legal assistant",
    "legal secretary", "training contract", "law firm", "legal intern",
    "lawyer", "barrister", "attorney",
    # Finance / Trading
    "trader", "graduate trader", "equity", "investment banking",
    "wealth management", "financial analyst", "banking",
    "fund accountant", "hedge fund", "asset management",
    "insurance", "loss adjuster", "claims adjuster",
    # Management / Business (non-surveying)
    "management trainee", "management associate",
    "business services", "business analyst",
    "graduate program", "graduate scheme", "graduate programme",
    "operations trainee", "operations management",
    "sourcing team", "procurement",
    "human resources", "hr trainee", "hr officer",
    # Engineering (unless title also has "surveyor" or "surveying")
    # We'll handle the engineer check in the function body
    "civil engineer", "structural engineer", "traffic engineer",
    "rail engineer", "geotechnical engineer", "transport planner",
    "electrical engineer", "mechanical engineer",
    "graduate engineer", "assistant engineer", "engineer -",
    "engineering graduate", "engineering trainee",
    "scheme \"a\" engineer",
    # Non-surveying graduate/trainee roles
    "property officer", "estate officer",
    "graduate intern", "sustainability intern",
    "town planner", "urban planner", "urban designer",
    "marketing", "sales", "business development",
    "accountant", "audit", "tax",
    "nurse", "teacher",
    # Company names that are clearly non-surveying
    "kpmg", "deloitte", "pwc", "ernst",
    "societe generale", "ralph lauren", "siemens",
    "clyde & co", "johnson stokes", "ankura",
    "dbs bank", "shangri-la", "hkt",
    "mashreq", "latham", "norton rose", "rpc ",
    "kennedys", "informa markets", "plaza premium",
    "ai insurance", "charles taylor",
    # Chinese non-surveying
    "环境", "土建", "土木", "施工", "财务", "人力资源",
    "教师", "护士",
    # Misc
    "quality surveyor",  # common typo/spam
]

# ── Discipline Classification ──
# Rules applied in priority order to title text
DISCIPLINE_RULES = [
    # Quantity Surveying
    ("quantity_surveying", ["quantity survey", "qs ", "cost manager", "cost consultant",
                             "cost estimate", "boq", "bills of quantities",
                             "commercial manager", "contracts manager"]),
    # Land Surveying
    ("land_surveying", ["land survey", "geomatics", "geospatial", "gis ",
                         "cadastral", "topographic", "hydrographic",
                         "lidar", "gnss", "boundary survey", "site survey"]),
    # Building Surveying
    ("building_surveying", ["building survey", "building inspection", "condition survey",
                             "dilapidation", "building maintenance", "facade",
                             "building pathology", "acm ", "asbestos", "ubw"]),
    # General Practice
    ("general_practice", ["general practice", "valuation survey", "property valuation",
                           "estate survey", "land administration",
                           "estate management", "property management"]),
    # Planning
    ("planning", ["planning survey", "town planning", "urban planning",
                   "development survey"]),
]


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def extract_closing_date(description: str, requirements: str = "", title: str = "") -> str:
    """Extract closing/application deadline date from job description text.

    Supports HK and international formats:
    - [Application Deadline: 24 May 2026]
    - 截止日期：2026年5月24日
    - Closing Date: 31 July 2026
    - Apply by: 2026-06-30
    - Application closing date: 2026/07/15
    - Deadline: 2026-08-01
    - Please apply before 30 June 2026

    Returns 'YYYY-MM-DD' string or empty string if not found.
    """
    text = f"{description} {requirements}"

    # Normalize text: remove zero-width chars, normalize whitespace
    text = text.replace("\u200b", "").replace("\u200c", "").replace("\u200d", "")
    text = " ".join(text.split())

    # Pattern 1: Named months (English)
    # [Application Deadline: 24 May 2026], Closing Date: 31 July 2026
    month_patterns = [
        r'(?:application\s*)?deadline[\s:：]*.*?(\d{1,2})\s+(January|February|March|April|May|June|July|August|September|October|November|December),?\s+(\d{4})',
        r'closing\s*date[\s:：]*.*?(\d{1,2})\s+(January|February|March|April|May|June|July|August|September|October|November|December),?\s+(\d{4})',
        r'apply\s*by[\s:：]*.*?(\d{1,2})\s+(January|February|March|April|May|June|July|August|September|October|November|December),?\s+(\d{4})',
        r'please\s*apply\s*before[\s:：]*.*?(\d{1,2})\s+(January|February|March|April|May|June|July|August|September|October|November|December),?\s+(\d{4})',
        r'deadline[\s:：]*.*?(\d{1,2})\s+(January|February|March|April|May|June|July|August|September|October|November|December),?\s+(\d{4})',
    ]

    month_map = {
        "january": 1, "february": 2, "march": 3, "april": 4,
        "may": 5, "june": 6, "july": 7, "august": 8,
        "september": 9, "october": 10, "november": 11, "december": 12,
    }

    for pattern in month_patterns:
        m = re.search(pattern, text, re.IGNORECASE)
        if m:
            day = int(m.group(1))
            month = month_map.get(m.group(2).lower())
            year = int(m.group(3))
            if 1 <= day <= 31 and month:
                return f"{year:04d}-{month:02d}-{day:02d}"

    # Pattern 2: Chinese dates
    # 截止日期：2026年5月24日, 截止日期: 2026-05-24
    chinese_patterns = [
        r'截止日期[：:]\s*(\d{4})\s*年\s*(\d{1,2})\s*月\s*(\d{1,2})\s*日',
        r'申請截止日期[：:]\s*(\d{4})\s*年\s*(\d{1,2})\s*月\s*(\d{1,2})\s*日',
        r'截止日期[：:]\s*(\d{4})[-/](\d{1,2})[-/](\d{1,2})',
        r'截止日期[：:].*?(\d{4})[-/](\d{1,2})[-/](\d{1,2})',
    ]

    for pattern in chinese_patterns:
        m = re.search(pattern, text)
        if m:
            year = int(m.group(1))
            month = int(m.group(2))
            day = int(m.group(3))
            if 1 <= day <= 31 and 1 <= month <= 12:
                return f"{year:04d}-{month:02d}-{day:02d}"

    # Pattern 3: Numeric dates (ISO or variations)
    # Deadline: 2026-08-01, Closing: 2026/06/30
    numeric_patterns = [
        r'(?:deadline|closing|apply by)[\s:：]*.*?(\d{4})[-/](\d{1,2})[-/](\d{1,2})',
        r'(\d{4})[-/](\d{1,2})[-/](\d{1,2})\s*(?:deadline|closing|截止)',
    ]

    for pattern in numeric_patterns:
        m = re.search(pattern, text, re.IGNORECASE)
        if m:
            year = int(m.group(1))
            month = int(m.group(2))
            day = int(m.group(3))
            if 2024 <= year <= 2027 and 1 <= month <= 12 and 1 <= day <= 31:
                return f"{year:04d}-{month:02d}-{day:02d}"

    # Pattern 4: Inline HK format [Deadline: 24-May-2026] and abbreviated months
    month_abbr = {
        "jan": 1, "feb": 2, "mar": 3, "apr": 4,
        "may": 5, "jun": 6, "jul": 7, "aug": 8,
        "sep": 9, "oct": 10, "nov": 11, "dec": 12,
    }
    month_abbr.update(month_map)
    
    inline_patterns = [
        r'deadline[\s:：]*\\]?\s*(\d{1,2})\s*[-–]\s*(January|February|March|April|May|June|July|August|September|October|November|December|Jan|Feb|Mar|Apr|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s*[-–]\s*(\d{4})',
        r'apply\s*(?:before|by)\s*(\d{1,2})\s*[-–]\s*(January|February|March|April|May|June|July|August|September|October|November|December|Jan|Feb|Mar|Apr|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s*[-–]\s*(\d{4})',
    ]

    for pattern in inline_patterns:
        m = re.search(pattern, text, re.IGNORECASE)
        if m:
            day = int(m.group(1))
            month = month_abbr.get(m.group(2).lower())
            year = int(m.group(3))
            if month:
                return f"{year:04d}-{month:02d}-{day:02d}"

    return ""


def make_external_id(title, company, source):
    raw = f"{title.lower().strip()}|{company.lower().strip()}|{source}"
    return hashlib.md5(raw.encode()).hexdigest()[:16]


def is_surveying_job(title, description=""):
    """Check if the job is actually a surveying role. Non-surveying jobs return False."""
    title_lower = title.lower()
    text = (title + " " + description).lower()

    # Check non-surveying keywords in title first (higher precision)
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

    # Also check description for non-surveying signals
    for kw in NON_SURVEYING_KEYWORDS:
        if kw in text:
            if ("engineer" in kw or "engineering" in kw or "scheme" in kw) and \
               ("surveyor" in title_lower or "surveying" in title_lower):
                continue
            if "surveyor" in title_lower or "surveying" in title_lower:
                continue
            return False

    # Must mention surveyor/surveying OR quantity surveyor-related terms
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


def classify_discipline_by_title(title, description=""):
    """Classify surveying discipline from title using DISCIPLINE_RULES in priority order."""
    text = (title + " " + description).lower()

    for discipline, keywords in DISCIPLINE_RULES:
        for kw in keywords:
            if kw in text:
                return discipline

    # Default fallback
    if "surveyor" in text or "surveying" in text:
        return "other"
    return "other"


def classify_experience_level(title, description=""):
    """Classify job into 3 tiers based on title and description text.

    Returns one of: "graduate", "entry", "experienced".

    Priority: Title-based signals > description-based signals.
    - Title "senior/manager/director" → experienced (regardless of description)
    - Title "graduate/trainee/intern" → graduate
    - Title "assistant/junior" → entry
    - Description "3+ years" → experienced
    - Description "0 years/fresh grad" → graduate
    - Description "1-2 years" → entry
    - Default → entry
    """
    title_lower = title.lower()
    text = (title + " " + description).lower()

    # ── PHASE 1: Title-level classification (strongest signal) ──

    # Check experienced title keywords FIRST
    EXPERIENCED_TITLE = [
        "senior", "manager", "director", "principal", "lead ",
        "chief surveyor", "resident land surveyor", "resident quantity surveyor",
        "resident building surveyor", "chartered surveyor", "mrics", "mhkis",
        "project quantity surveyor", "project surveyor",
    ]
    for kw in EXPERIENCED_TITLE:
        if kw in title_lower:
            return "experienced"

    # Graduate/intern title keywords
    GRADUATE_TITLE = [
        "graduate", "intern", "trainee", "scheme a", "apc",
        "2026 intake", "2026 graduate", "2026 fresh",
    ]
    for kw in GRADUATE_TITLE:
        if kw in title_lower:
            # But if ALSO has "senior" anywhere in text, recheck
            for ekw in ["3+ year", "5 year", "5+ year", "8 year", "10 year",
                          "minimum 3", "minimum 5", "min. 3", "min. 5",
                          "post-qualification", "registered surveyor"]:
                if ekw in text:
                    return "experienced"
            return "graduate"

    # Entry title keywords
    ENTRY_TITLE = [
        "assistant", "junior", "entry level", "entry-level",
        "apprentice", "early career",
    ]
    for kw in ENTRY_TITLE:
        if kw in title_lower:
            # But if description says 3+ years, recheck
            for ekw in ["3+ year", "5 year", "5+ year", "8 year", "10 year",
                          "minimum 3", "minimum 5", "min. 3", "min. 5",
                          "at least 3", "at least 5"]:
                if ekw in text:
                    return "experienced"
            return "entry"

    # ── PHASE 2: Description-level classification (weaker signal) ──

    # Check experienced descriptions
    for kw in EXPERIENCED_KEYWORDS:
        if kw in text:
            return "experienced"

    # Check graduate descriptions (only true graduate/structured programs)
    GRADUATE_DESC = [
        "no experience", "0 year", "0 yr",
        "scheme a", "apc programme", "apc program",
        "graduate programme", "graduate program",
    ]
    for kw in GRADUATE_DESC:
        if kw in text:
            return "graduate"

    # Check entry descriptions
    ENTRY_DESC = [
        "0-1", "1 year", "1 yr", "1-2", "2 year", "2 yr",
        "less experience", "willing to learn", "training provided",
    ]
    for kw in ENTRY_DESC:
        if kw in text:
            return "entry"

    # Default: assume entry-level
    return "entry"


def insert_job(conn, job: dict):
    ext_id = make_external_id(job["title"], job["company"], job["source"])

    # ── Pre-insert filtering ──
    # 1. Non-surveying jobs: skip entirely
    desc = job.get("description", "") + " " + job.get("requirements", "")
    if not is_surveying_job(job["title"], desc):
        return None

    # 2. Override discipline with title-based classification
    detected_disc = classify_discipline_by_title(job["title"], job.get("description", ""))
    if detected_disc != "other" or job.get("discipline") == "other":
        job["discipline"] = detected_disc

    # 3. Classify experience level
    exp_tier = classify_experience_level(job["title"], desc)

    existing = conn.execute(
        "SELECT id FROM jobs WHERE external_id = ?", (ext_id,)
    ).fetchone()
    if existing:
        return None

    conn.execute(
        """INSERT INTO jobs
           (external_id, title, company, discipline, location, salary_range,
            description, requirements, url, source, posted_date, closing_date,
            fresh_grad_friendly, experience_level)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (
            ext_id, job["title"], job["company"], job["discipline"],
            job.get("location", "Hong Kong"), job.get("salary_range"),
            job.get("description", ""), job.get("requirements", ""),
            job.get("url", ""), job["source"], job.get("posted_date", datetime.now().strftime("%Y-%m-%d")),
            extract_closing_date(job.get("description", ""), job.get("requirements", "")),
            1 if exp_tier in ("graduate", "entry") else 0,
            exp_tier,
        ),
    )
    return conn.execute("SELECT last_insert_rowid()").fetchone()[0]


def scrape_ctgoodjobs(url: str, discipline: str) -> list[dict]:
    """Scrape CTgoodjobs search results page. Titles and companies are server-rendered."""
    jobs = []
    try:
        resp = httpx.get(
            url,
            headers={"User-Agent": USER_AGENT, "Accept-Language": "en-US,en;q=0.9,zh-HK;q=0.8"},
            follow_redirects=True, timeout=30,
        )
        if resp.status_code != 200:
            print(f"    CTgoodjobs HTTP {resp.status_code} for {url}")
            return jobs

        soup = BeautifulSoup(resp.text, "html.parser")

        # CTgoodjobs renders job cards with various patterns
        # Pattern 1: job-card style containers
        cards = soup.select('[class*="job-card"], [class*="job-item"], [class*="job-listing"]')
        if not cards:
            # Pattern 2: try link-based extraction
            cards = soup.select('a[href*="/job/"]')

        seen = set()
        for card in cards:
            # Extract title
            title_el = (
                card.select_one('[class*="job-title"]') or
                card.select_one('[class*="title"]') or
                card.select_one('h2, h3, h4')
            )
            title = title_el.get_text(strip=True) if title_el else ""

            # Extract company
            company_el = (
                card.select_one('[class*="company"]') or
                card.select_one('[class*="employer"]')
            )
            company = company_el.get_text(strip=True) if company_el else "Unknown"

            # Extract link
            link_el = card if card.name == "a" and card.get("href") else card.select_one("a[href]")
            link = link_el.get("href", "") if link_el else ""
            if link and not link.startswith("http"):
                link = urljoin("https://jobs.ctgoodjobs.hk", link)

            # Skip if too generic
            if not title or len(title) < 5:
                continue
            if "search" in title.lower() and "job" not in title.lower():
                continue

            dedup_key = f"{title}|{company}"
            if dedup_key in seen:
                continue
            seen.add(dedup_key)

            # Non-surveying filter
            if not is_surveying_job(title):
                continue

            # Override discipline
            detected_disc = classify_discipline_by_title(title)
            job_discipline = detected_disc if detected_disc != "other" else discipline

            # Experience level
            exp_tier = classify_experience_level(title)

            jobs.append({
                "title": html.unescape(title),
                "company": html.unescape(company),
                "discipline": job_discipline,
                "location": "Hong Kong",
                "source": "ctgoodjobs",
                "url": link,
                "posted_date": datetime.now().strftime("%Y-%m-%d"),
                "fresh_grad_friendly": True,
            })

    except Exception as e:
        print(f"    CTgoodjobs error: {e}")

    return jobs


def scrape_indeed(url: str, discipline: str) -> list[dict]:
    """Try Indeed — likely blocked by Cloudflare, but attempt with proper headers."""
    jobs = []
    try:
        resp = httpx.get(
            url,
            headers={
                "User-Agent": USER_AGENT,
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.9",
            },
            follow_redirects=True, timeout=30,
        )
        if resp.status_code != 200:
            print(f"    Indeed HTTP {resp.status_code} — blocked, skipping")
            return jobs

        soup = BeautifulSoup(resp.text, "html.parser")

        # Indeed job cards: jobTitle span + companyName span
        titles = soup.select('h2.jobTitle span[title], h2.jobTitle a, a[data-jk] span')
        companies = soup.select('span[data-testid="company-name"], span.companyName')

        seen = set()
        for i, title_el in enumerate(titles):
            title = title_el.get_text(strip=True)
            company = companies[i].get_text(strip=True) if i < len(companies) else "Unknown"

            if not title or len(title) < 5:
                continue
            dedup_key = f"{title}|{company}"
            if dedup_key in seen:
                continue
            seen.add(dedup_key)

            # Non-surveying filter
            if not is_surveying_job(title):
                continue

            # Override discipline
            detected_disc = classify_discipline_by_title(title)
            job_discipline = detected_disc if detected_disc != "other" else discipline

            # Experience level
            exp_tier = classify_experience_level(title)

            jobs.append({
                "title": title,
                "company": company,
                "discipline": job_discipline,
                "location": "Hong Kong",
                "source": "indeed",
                "url": url,
                "posted_date": datetime.now().strftime("%Y-%m-%d"),
                "fresh_grad_friendly": True,
            })

    except Exception as e:
        print(f"    Indeed error: {e}")

    return jobs


def scrape_linkedin(url: str, discipline: str) -> list[dict]:
    """LinkedIn search — extract job titles from the search results page.
    Details are behind auth wall, but title/company/link are visible."""
    jobs = []
    try:
        resp = httpx.get(
            url,
            headers={
                "User-Agent": USER_AGENT,
                "Accept-Language": "en-US,en;q=0.9",
            },
            follow_redirects=True, timeout=30,
        )
        if resp.status_code != 200:
            print(f"    LinkedIn HTTP {resp.status_code}")
            return jobs

        soup = BeautifulSoup(resp.text, "html.parser")

        # LinkedIn renders job cards server-side with base-card class
        cards = soup.select('.base-card, .job-search-card, [class*="job-card"]')
        if not cards:
            # Fallback: look for job title links
            cards = soup.select('a[href*="/jobs/view/"]')

        seen = set()
        for card in cards:
            title_el = (
                card.select_one('.base-search-card__title, .job-search-card__title, h3') or
                card
            )
            title = title_el.get_text(strip=True) if title_el else ""

            company_el = card.select_one('.base-search-card__subtitle, .job-search-card__subtitle, h4')
            company = company_el.get_text(strip=True) if company_el else "Unknown"

            link_el = card if card.name == "a" else card.select_one("a[href]")
            link = link_el.get("href", "") if link_el else ""
            if link and not link.startswith("http"):
                link = urljoin("https://hk.linkedin.com", link)

            if not title or len(title) < 5:
                continue
            dedup_key = f"{title}|{company}"
            if dedup_key in seen:
                continue
            seen.add(dedup_key)

            # Non-surveying filter
            if not is_surveying_job(title):
                continue

            # Override discipline
            detected_disc = classify_discipline_by_title(title)
            job_discipline = detected_disc if detected_disc != "other" else discipline

            # Experience level
            exp_tier = classify_experience_level(title)

            jobs.append({
                "title": html.unescape(title),
                "company": html.unescape(company),
                "discipline": job_discipline,
                "location": "Hong Kong",
                "source": "linkedin",
                "url": link,
                "posted_date": datetime.now().strftime("%Y-%m-%d"),
                "fresh_grad_friendly": True,
            })

    except Exception as e:
        print(f"    LinkedIn error: {e}")

    return jobs




def scrape_hkis() -> list[dict]:
    """Scrape HKIS (Hong Kong Institute of Surveyors) official job board.
    
    URL: https://www.hkis.org.hk/en/jobs.html?division=&keyword=&S=5
    Server-side rendered table with Title, Company, Post Date columns.
    """
    jobs = []
    url = "https://www.hkis.org.hk/en/jobs.html?division=&keyword=&S=5"
    try:
        resp = httpx.get(
            url,
            headers={"User-Agent": USER_AGENT, "Accept-Language": "en-US,en;q=0.9,zh-HK;q=0.8"},
            follow_redirects=True, timeout=30,
        )
        if resp.status_code != 200:
            print(f"    HKIS HTTP {resp.status_code}")
            return jobs

        soup = BeautifulSoup(resp.text, "html.parser")
        
        # HKIS job board uses a standard table
        table = soup.select_one("table")
        if not table:
            print("    HKIS: no table found")
            return jobs

        rows = table.select("tr")[1:]  # Skip header row
        seen = set()
        for row in rows:
            cols = row.select("td")
            if len(cols) < 3:
                continue
            
            title_el = cols[0].select_one("a")
            title = title_el.get_text(strip=True) if title_el else cols[0].get_text(strip=True)
            link = title_el.get("href", "") if title_el else ""
            if link and not link.startswith("http"):
                link = urljoin("https://www.hkis.org.hk", link)
            
            company = cols[1].get_text(strip=True) if len(cols) > 1 else "Unknown"
            post_date = cols[2].get_text(strip=True) if len(cols) > 2 else datetime.now().strftime("%Y-%m-%d")
            
            if not title or len(title) < 5:
                continue
            if "search" in title.lower():
                continue
            
            dedup_key = f"{title}|{company}"
            if dedup_key in seen:
                continue
            seen.add(dedup_key)
            
            # Non-surveying filter
            if not is_surveying_job(title):
                continue
            
            # Classify
            job_discipline = classify_discipline_by_title(title)
            exp_tier = classify_experience_level(title)
            
            jobs.append({
                "title": html.unescape(title),
                "company": html.unescape(company),
                "discipline": job_discipline,
                "location": "Hong Kong",
                "source": "hkis",
                "url": link,
                "posted_date": post_date,
                "fresh_grad_friendly": True,
            })
    
    except Exception as e:
        print(f"    HKIS error: {e}")
    
    return jobs

def main(skip_backfill=False):
    conn = get_db()
    new_count = 0
    total_found = 0
    platform_stats = {}

    print(f"=== Scrape run: {datetime.now().isoformat()} ===")

    # 1. Google Jobs (primary source — aggregates all boards)
    print("\n--- Google Jobs (primary) ---")
    for query, discipline, location in GOOGLE_QUERIES:
        print(f"  [google] {discipline}: {query[:60]}...")
        results = search_google_jobs(query, location, discipline)
        platform_stats["google_jobs"] = platform_stats.get("google_jobs", 0) + len(results)
        total_found += len(results)
        for job in results:
            rid = insert_job(conn, job)
            if rid:
                new_count += 1
                print(f"    NEW #{rid}: {job['title'][:60]} @ {job['company'][:30]} [{job['discipline']}]")
        time.sleep(1.5)

    # 2. HKIS official job board
    print("\n--- HKIS (official surveying institute) ---")
    hkis_results = scrape_hkis()
    platform_stats["hkis"] = len(hkis_results)
    total_found += len(hkis_results)
    for job in hkis_results:
        rid = insert_job(conn, job)
        if rid:
            new_count += 1
            print(f"    NEW #{rid}: {job['title'][:60]} @ {job['company'][:30]} [{job['discipline']}]")

    # 3. LinkedIn fallback (complementary, different results sometimes)
    print("\n--- LinkedIn (fallback) ---")
    for platform, url, discipline in SEARCH_CONFIGS:
        if platform != "linkedin":
            continue
        print(f"  [{platform}] {discipline}: {url[:80]}...")
        results = scrape_linkedin(url, discipline)
        platform_stats[platform] = platform_stats.get(platform, 0) + len(results)
        total_found += len(results)
        for job in results:
            rid = insert_job(conn, job)
            if rid:
                new_count += 1
                print(f"    NEW #{rid}: {job['title'][:60]} @ {job['company'][:30]}")
        time.sleep(1.0)

    conn.commit()
    total_db = conn.execute("SELECT COUNT(*) FROM jobs WHERE is_active=1").fetchone()[0]

    # Breakdown by discipline
    breakdown = {}
    for row in conn.execute(
        "SELECT discipline, COUNT(*) as cnt FROM jobs WHERE is_active=1 GROUP BY discipline ORDER BY cnt DESC"
    ):
        breakdown[row["discipline"]] = row["cnt"]

    conn.close()

    # --- Backfill: fill in descriptions (skippable for manual refresh) ---
    if skip_backfill:
        backfill_result = {"skipped": True, "note": "backfill skipped via --skip-backfill"}
        print("    Backfill skipped (--skip-backfill)")
    else:
        backfill_result = backfill_all(DB_PATH, verbose=True)

    result = {
        "timestamp": datetime.now().isoformat(),
        "total_found": total_found,
        "new_jobs": new_count,
        "total_in_db": total_db,
        "by_platform": platform_stats,
        "by_discipline": breakdown,
        "backfill": backfill_result,
    }

    print(f"\nDone. Found {total_found}, added {new_count} new. DB now has {total_db} jobs.")
    print(f"By discipline: {breakdown}")
    print(json.dumps(result, indent=2))
    return result


if __name__ == "__main__":
    import sys
    skip = "--skip-backfill" in sys.argv
    main(skip_backfill=skip)
