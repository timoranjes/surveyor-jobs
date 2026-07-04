#!/usr/bin/env python3
"""
HTML description scraper — fetches original job pages and extracts formatted content.
Generic approach: tries common job description selectors, falls back to body content.
Sanitizes HTML to keep only formatting tags (headings, paragraphs, lists, bold, etc.).
"""

import re
import httpx
from bs4 import BeautifulSoup, Comment

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)

# Tags to keep (formatting + structure only)
KEEP_TAGS = {
    'h1', 'h2', 'h3', 'h4', 'h5', 'h6',
    'p', 'br', 'hr',
    'ul', 'ol', 'li',
    'strong', 'b', 'em', 'i', 'u',
    'table', 'thead', 'tbody', 'tr', 'th', 'td',
    'div', 'span', 'section', 'article',
    'a', 'blockquote', 'pre', 'code',
}

# Tags that may contain the job description body
DESCRIPTION_SELECTORS = [
    # Indeed
    '#jobDescriptionText',
    '[data-testid="jobDescriptionText"]',
    # Generic job board patterns
    '[class*="job-description"]',
    '[class*="jobdescription"]',
    '[class*="description"]',
    '[class*="job-detail"]',
    '[class*="jobdetail"]',
    '[class*="jd-container"]',
    '[id*="job-description"]',
    '[id*="jobdescription"]',
    # CTgoodjobs
    '[class*="job-detail-content"]',
    '[class*="job-requirement"]',
    # LinkedIn
    '.description__text',
    '.show-more-less-html__markup',
    '[class*="jobs-description"]',
    # Glassdoor
    '[class*="jobDescriptionContent"]',
    '.desc',
    # Jooble / aggregators
    '[class*="job-text"]',
    '[data-testid="job-details"]',
    'article',
]

# Blacklisted tags — remove entirely
REMOVE_TAGS = {
    'script', 'style', 'noscript', 'iframe', 'svg',
    'nav', 'footer', 'header', 'aside', 'form',
    'input', 'button', 'select', 'textarea',
    'meta', 'link',
}

# Blacklisted class/id patterns — remove elements matching these
REMOVE_PATTERNS = [
    'nav', 'menu', 'sidebar', 'footer', 'header-bar',
    'cookie', 'banner', 'popup', 'modal', 'overlay',
    'advertisement', 'ad-', 'social', 'share',
    'related-jobs', 'similar-jobs', 'apply-button',
    'pagination', 'breadcrumb',
]


def sanitize_html(soup: BeautifulSoup) -> str:
    """Clean a BeautifulSoup tree: remove junk, keep only relevant formatting tags."""
    
    # Remove blacklisted tags
    for tag_name in REMOVE_TAGS:
        for tag in soup.find_all(tag_name):
            tag.decompose()
    
    # Remove comments
    for comment in soup.find_all(string=lambda text: isinstance(text, Comment)):
        comment.extract()
    
    # Remove elements with blacklisted class/id patterns
    for tag in soup.find_all(True):
        if not hasattr(tag, 'name') or tag.name is None:
            continue
        if not hasattr(tag, 'attrs') or tag.attrs is None:
            continue
        classes = ' '.join(tag.get('class') or [])
        tag_id = tag.get('id', '') or ''
        combined = f"{classes} {tag_id}".lower()
        if any(pattern in combined for pattern in REMOVE_PATTERNS):
            tag.decompose()
            continue
    
    # Strip all attributes except href on <a> tags
    for tag in soup.find_all(True):
        if not hasattr(tag, 'name') or tag.name is None:
            continue
        attrs_to_keep = {}
        if tag.name == 'a' and tag.get('href'):
            attrs_to_keep['href'] = tag['href']
            # Make links open in new tab
            attrs_to_keep['target'] = '_blank'
            attrs_to_keep['rel'] = 'noopener noreferrer'
        tag.attrs = attrs_to_keep
    
    # Remove empty tags (recursively, bottom-up)
    for tag in soup.find_all(True):
        if tag.name not in ('br', 'hr', 'img') and not tag.get_text(strip=True):
            tag.decompose()
    
    # Get the body content
    body = soup.find('body')
    if body:
        return str(body)
    return str(soup)


def extract_description(html: str, url: str = "") -> str | None:
    """Extract the job description portion from an HTML page.
    
    Tries known selectors first, falls back to body content.
    Returns sanitized HTML string or None if extraction fails.
    """
    soup = BeautifulSoup(html, 'html.parser')
    
    # Try each known selector
    for selector in DESCRIPTION_SELECTORS:
        elements = soup.select(selector)
        for el in elements:
            text = el.get_text(strip=True)
            # Must have meaningful content (>200 chars)
            if len(text) > 200:
                # Found a good candidate — sanitize just this element
                return sanitize_html(el)
    
    # Fallback: use the entire body but try to be smart about it
    body = soup.find('body')
    if not body:
        return None
    
    # Try to find the main content area
    main = (
        body.find('main') or
        body.find(attrs={'role': 'main'}) or
        body.select_one('[class*="main-content"]') or
        body.select_one('[class*="content"]')
    )
    
    target = main or body
    text = target.get_text(strip=True)
    
    if len(text) < 200:
        # Too little content — probably a JS-rendered page or auth wall
        return None
    
    return sanitize_html(target)


def fetch_job_page(url: str, timeout: int = 15) -> str | None:
    """Fetch a job page and return its HTML content."""
    try:
        resp = httpx.get(
            url,
            headers={
                "User-Agent": USER_AGENT,
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.9,zh-HK;q=0.8",
            },
            follow_redirects=True,
            timeout=timeout,
        )
        if resp.status_code != 200:
            return None
        return resp.text
    except Exception:
        return None


def scrape_description_html(url: str) -> str | None:
    """Main entry point: fetch a job page and extract its formatted description.
    
    Returns sanitized HTML string, or None if the page can't be fetched
    or doesn't contain enough content.
    """
    html = fetch_job_page(url)
    if not html:
        return None
    
    desc_html = extract_description(html, url)
    if not desc_html:
        return None
    
    # Trim to a reasonable size (50KB max)
    if len(desc_html) > 50000:
        desc_html = desc_html[:50000]
    
    return desc_html


if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print("Usage: python3 html_scraper.py <url>")
        sys.exit(1)
    
    url = sys.argv[1]
    print(f"Fetching: {url}")
    result = scrape_description_html(url)
    if result:
        print(f"Extracted {len(result)} chars of HTML")
        # Print first 500 chars
        print(result[:500])
    else:
        print("Failed to extract description")
