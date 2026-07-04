#!/usr/bin/env python3
"""
Backfill job descriptions for LinkedIn-only jobs using Google Jobs API.
Google indexes LinkedIn job content, so we can find descriptions by searching
for the exact company + title on Google Jobs.

Also generates description_html from plain-text descriptions using the
description_formatter for all jobs that don't have HTML yet.
"""

import os
import sys
import time
import sqlite3
from urllib.parse import urlencode
from difflib import SequenceMatcher

import httpx

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(PROJECT_ROOT, "data", "jobs.db")

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from description_formatter import convert_description
from html_scraper import scrape_description_html

SERPAPI_BASE = "https://serpapi.com/search"

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


def similarity(a, b):
    """String similarity 0-1."""
    return SequenceMatcher(None, a.lower(), b.lower()).ratio()


def _is_scrapable_url(url: str) -> bool:
    """Check if a URL looks directly scrapable (company career page, not aggregator)."""
    skip_domains = [
        'bebee.com', 'jobleads.com', 'jooble.org', 'jobrapido.com',
        'indeed.com', 'linkedin.com', 'glassdoor', 'cpjobs.com',
        'offertoday.com', 'kdphd.com', 'expatjobboard.com',
    ]
    url_lower = url.lower()
    for d in skip_domains:
        if d in url_lower:
            return False
    # Skip Google redirect URLs
    if 'google' in url_lower and 'utm' in url_lower:
        return False
    return True


def search_google_for_job(company: str, title: str) -> dict | None:
    """Search Google Jobs for a specific company + title. Returns best match with description."""
    api_key = _get_key()
    if not api_key:
        return None

    # Build targeted query
    query = f'"{title}" "{company}" Hong Kong'
    params = {
        "engine": "google_jobs",
        "q": query,
        "location": "Hong Kong",
        "hl": "en",
        "gl": "hk",
        "api_key": api_key,
    }

    try:
        resp = httpx.get(f"{SERPAPI_BASE}?{urlencode(params)}", timeout=30)
        if resp.status_code != 200:
            return None

        data = resp.json()
        if "error" in data:
            return None

        results = data.get("jobs_results", [])
        if not results:
            return None

        # Find best match by company + title similarity
        best = None
        best_score = 0
        for jr in results:
            g_company = jr.get("company_name", "")
            g_title = jr.get("title", "")
            g_desc = jr.get("description", "")

            if not g_desc or len(g_desc) < 100:
                continue

            company_score = similarity(company, g_company)
            title_score = similarity(title, g_title)
            total_score = (company_score * 0.6) + (title_score * 0.4)

            if total_score > best_score and total_score > 0.5:
                best_score = total_score
                best = {
                    "description": g_desc[:3000],
                    "matched_title": g_title,
                    "matched_company": g_company,
                    "score": total_score,
                }

        return best

    except Exception as e:
        print(f"    Error: {e}")
        return None


def backfill_all(db_path: str = DB_PATH, verbose: bool = True) -> dict:
    """Find all jobs without descriptions and backfill from Google Jobs.
    Also populate description_html for jobs that have plain text but no HTML.
    
    Args:
        db_path: Path to the SQLite database.
        verbose: Print progress messages.
    
    Returns:
        dict with 'updated', 'skipped', 'total_checked', 'html_generated' counts.
    """
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    # Find jobs without descriptions
    rows = conn.execute(
        """SELECT id, title, company, url FROM jobs
           WHERE is_active=1 AND (description='' OR description IS NULL OR length(description)<50)
           ORDER BY id"""
    ).fetchall()

    if not rows:
        if verbose:
            print("All jobs already have descriptions.")
    else:
        if verbose:
            print(f"\n--- Backfill: {len(rows)} jobs without descriptions ---")

        updated = 0
        skipped = 0
        for row in rows:
            job_id = row["id"]
            title = row["title"]
            company = row["company"]

            if verbose:
                print(f"  [{job_id}] {title[:55]} @ {company}")

            result = search_google_for_job(company, title)

            if result:
                desc = result["description"]
                matched = result["matched_title"]
                score = result["score"]

                conn.execute(
                    "UPDATE jobs SET description=? WHERE id=?",
                    (desc, job_id),
                )
                conn.commit()
                updated += 1
                if verbose:
                    print(f"    ✅ Found JD (score: {score:.0%}, matched: {matched[:50]})")
                    print(f"    📝 {len(desc)} chars: {desc[:120]}...")
            else:
                skipped += 1
                if verbose:
                    print(f"    ⚠️  No match found on Google Jobs")

            time.sleep(1.0)  # Rate limit

        if verbose:
            print(f"  Backfill done: {updated} updated, {skipped} skipped.\n")

    # ── Phase 2: Generate description_html for all jobs that have plain text but no HTML ──
    html_rows = conn.execute(
        """SELECT id, title, company, description, url, source FROM jobs
           WHERE is_active=1 
             AND description != '' AND description IS NOT NULL
             AND (description_html = '' OR description_html IS NULL)
           ORDER BY id"""
    ).fetchall()

    html_generated = 0
    html_from_source = 0

    if html_rows:
        if verbose:
            print(f"\n--- HTML Generation: {len(html_rows)} jobs to process ---")

        for row in html_rows:
            job_id = row["id"]
            title = row["title"]
            company = row["company"]
            description = row["description"]
            url = row["url"]

            if verbose:
                print(f"  [{job_id}] {title[:55]} @ {company}")

            html = None

            # Strategy 1: Try to scrape original page (best quality)
            # Only attempt for URLs that look directly scrapable (skip aggregators, short links)
            if url and _is_scrapable_url(url):
                html = scrape_description_html(url)
                if html and verbose:
                    print(f"    🎯 Got HTML from source page ({len(html)} chars)")

            # Strategy 2: Convert plain text to structured HTML (fallback)
            if not html and description:
                html = convert_description(description)
                if verbose:
                    print(f"    📄 Generated HTML from plain text ({len(html)} chars)")

            if html:
                conn.execute(
                    "UPDATE jobs SET description_html=? WHERE id=?",
                    (html, job_id),
                )
                conn.commit()
                html_generated += 1
            else:
                if verbose:
                    print(f"    ⚠️  No HTML could be generated")

        if verbose:
            print(f"  HTML generation done: {html_generated} generated.\n")

    conn.close()
    
    # Count vars might not be defined if no description backfill ran
    updated = locals().get('updated', 0)
    skipped = locals().get('skipped', 0)
    total_checked = len(rows) if 'rows' in dir() else 0
    
    return {
        "updated": updated,
        "skipped": skipped,
        "total_checked": total_checked,
        "html_generated": html_generated,
    }


if __name__ == "__main__":
    backfill_all()
