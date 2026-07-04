#!/usr/bin/env python3
"""
Plain-text to structured HTML formatter for job descriptions.
Converts Google Jobs plain-text descriptions into clean, readable HTML
that approximates the original site's formatting.

v2: Line-by-line state-machine approach — handles Google's inconsistent
    newline patterns for bullets, headers, and paragraphs.
"""

import re
import html as html_mod


# Known section headers (case-insensitive matching)
SECTION_HEADERS = [
    # Company/role intro
    r'^Company\s+Description\s*$',
    r'^Company\s+Description\b',  # Catches "Company DescriptionWho..." run-ons
    r'^About\s+(?:the\s+)?(?:Company|Us|This\s+Role)\s*$',
    r'^Role\s+Description\s*:?\s*$',
    r'^Job\s+Description\s*:?\s*$',
    r'^Position\s+Overview\s*:?\s*$',
    r'^Overview\s*:?\s*$',
    r'^The\s+Role\s*:?\s*$',
    r'^What\s+is\s+.+\?\s*$',  # "What is Engineering Graduate Trainee about?"
    # Responsibilities
    r'^Responsibilities?\s*:?\s*$',
    r'^Key\s+Responsibilities?\s*:?\s*$',
    r'^Role\s+Accountabilities?\s*:?\s*$',
    r'^What\s+You[\u2019\']ll\s+Do\s*:?\s*$',
    r'^Duties?\s*(?:&|and)\s+Responsibilities?\s*:?\s*$',
    r'^Main\s+Responsibilities?\s*:?\s*$',
    r'^Principal\s+Responsibilities?\s*:?\s*$',
    r'^Your\s+Responsibilities?\s*:?\s*$',
    r'^Your\s+Role\s*:?\s*$',
    r'^Job\s+Duties?\s*:?\s*$',
    r'^Key\s+Duties?\s*:?\s*$',
    r'^Principal\s+Duties?\s*:?\s*$',
    r'^Main\s+Duties?\s*:?\s*$',
    # Requirements / Qualifications
    r'^Requirements?\s*:?\s*$',
    r'^Qualifications?\s*:?\s*$',
    r'^Qualifications?\s*(?:&|and)\s+Requirements?\s*:?\s*$',
    r'^Qualifications?\s*(?:&|and)\s+Experience\s*:?\s*$',
    r'^Key\s+Requirements?\s*:?\s*$',
    r'^What\s+We[\u2019\']re?\s+Looking\s+For\s*:?\s*$',
    r'^What\s+You[\u2019\']ll?\s+Need\s*:?\s*$',
    r'^Minimum\s+Requirements?\s*:?\s*$',
    r'^Preferred\s+Qualifications?\s*:?\s*$',
    r'^Required\s+Qualifications?\s*:?\s*$',
    r'^Required\s+Skills?\s*:?\s*$',
    r'^Your\s+Qualifications?\s*:?\s*$',
    r'^Who\s+We[\u2019\']re?\s+Looking\s+For\s*:?\s*$',
    r'^Who\s+You\s+Are\s*:?\s*$',
    r'^Ideal\s+Candidate\s*:?\s*$',
    r'^Requirements?\s+and\s+Qualifications?\s*:?\s*$',
    r'^Essential\s+Requirements?\s*:?\s*$',
    r'^Entry\s+Requirements?\s*:?\s*$',
    r'^General\s+Entrance\s+Requirements?\s*:?\s*$',
    r'^English\s+Language\s+Requirements?\s*:?\s*$',
    r'^Academic\s+Requirements?\s*:?\s*$',
    r'^Job\s+Requirements?\s*:?\s*$',
    r'^Skill\s*(?:&|and)\s+Competenc(?:y|ies)\s*:?\s*$',
    r'^Desired\s+Skills?\s*:?\s*$',
    # What we offer / Benefits
    r'^What\s+We\s+Offer\s*:?\s*$',
    r'^Benefits?\s*:?\s*$',
    r'^Compensation\s*(?:&|and)\s+Benefits?\s*:?\s*$',
    r'^Why\s+(?:Join|Work\s+(?:with|at))\s+(?:Us|Them)\s*:?\s*$',
    r'^Our\s+Offer\s*:?\s*$',
    r'^What[\u2019\']s\s+In\s+It\s+For\s+You\s*:?\s*$',
    r'^What\s+You[\u2019\']ll?\s+Get\s*:?\s*$',
    r'^Rewards?\s*(?:&|and)\s+Benefits?\s*:?\s*$',
    r'^Company\s+Benefits?\s*:?\s*$',
    r'^Remuneration\s*:?\s*$',
    # Additional info
    r'^Additional\s+Information\s*:?\s*$',
    r'^How\s+to\s+Apply\s*:?\s*$',
    r'^Equal\s+Opportunity\s*:?\s*$',
    r'^About\s+the\s+Team\s*:?\s*$',
    r'^About\s+This\s+Role\s*:?\s*$',
    r'^The\s+Opportunity\s*:?\s*$',
    r'^Our\s+Values?\s*:?\s*$',
    r'^Diversity\s*(?:&|and)\s+Inclusion\s*:?\s*$',
    r'^Work\s+Environment\s*:?\s*$',
    r'^Career\s+Development\s*:?\s*$',
    r'^Job\s+Details?\s*:?\s*$',
    r'^Job\s+Summary\s*:?\s*$',
    r'^Employment\s+Type\s*:?\s*$',
    r'^Location\s*:?\s*$',
    r'^Salary\s*:?\s*$',
    r'^Contract\s+Type\s*:?\s*$',
    r'^Working\s+Hours?\s*:?\s*$',
    r'^Reports\s+To\s*:?\s*$',
    r'^Department\s*:?\s*$',
    r'^Closing\s+Date\s*:?\s*$',
    r'^Start\s+Date\s*:?\s*$',
]

SECTION_PATTERNS = [re.compile(p, re.IGNORECASE) for p in SECTION_HEADERS]


def is_section_header(line: str) -> bool:
    """Check if a line looks like a section header."""
    line = line.strip()
    if not line or len(line) > 60:
        return False
    
    # Short all-caps lines are often headers (but not single words)
    if len(line) <= 40 and line.isupper() and len(line.split()) >= 2:
        return True
    
    for pattern in SECTION_PATTERNS:
        if pattern.match(line):
            return True
    
    return False


def find_inline_header(line: str) -> tuple[str | None, str]:
    """Check if a line contains a section header mid-text.
    Returns (header_text, rest_of_line) or (None, original_line).
    Example: 'Duties & Responsibilities Responsible for...' → ('Duties & Responsibilities', 'Responsible for...')
    """
    stripped = line.strip()
    for pattern in SECTION_PATTERNS:
        # Remove end-of-line anchor to match headers mid-text
        p = re.compile(pattern.pattern.replace('$', ''), re.IGNORECASE)
        m = p.match(stripped)
        if m:
            header = m.group().rstrip(':').strip()
            rest = stripped[m.end():].strip()
            if rest:
                return header, rest
    return None, line


def is_explicit_bullet(line: str) -> tuple[bool, str, str]:
    """Check if a line starts with an explicit bullet character.
    Returns (is_bullet, bullet_char, rest)."""
    line_stripped = line.lstrip()
    
    bullet_patterns = [
        (r'^[•●○◦▪▸►▻»→]\s+', '•'),
        (r'^[-–—]\s+', '–'),
        (r'^[\*]\s+', '•'),
        (r'^\d+[\.\)]\s+', None),
        (r'^[a-zA-Z][\.\)]\s+', None),
    ]
    
    for pattern, default_char in bullet_patterns:
        m = re.match(pattern, line_stripped)
        if m:
            rest = line_stripped[m.end():]
            bullet = m.group().strip() if default_char is None else default_char
            return True, bullet, rest
    
    return False, '', line


def is_likely_content_line(line: str) -> bool:
    """Check if a line looks like substantive content (not a header, not whitespace)."""
    stripped = line.strip()
    if not stripped:
        return False
    if is_section_header(stripped):
        return False
    return len(stripped) > 5


def format_plain_to_html(text: str) -> str:
    """Convert plain-text job description to structured HTML using line-by-line state machine."""
    if not text or not text.strip():
        return ''
    
    # Normalize
    text = text.strip()
    text = re.sub(r'\r\n|\r', '\n', text)
    text = re.sub(r'\n{3,}', '\n\n', text)
    
    lines = text.split('\n')
    
    html_parts = []
    state = 'para'        # 'para' | 'bullets'
    para_buffer = []      # Accumulates paragraph lines
    bullet_buffer = []    # Accumulates bullet items
    
    def flush_para():
        nonlocal para_buffer
        if para_buffer:
            content = ' '.join(para_buffer)
            html_parts.append(f'<p>{_format_inline(html_mod.escape(content))}</p>')
            para_buffer = []
    
    def flush_bullets():
        nonlocal bullet_buffer
        if bullet_buffer:
            items = ''.join(f'<li>{_format_inline(html_mod.escape(b))}</li>' for b in bullet_buffer)
            html_parts.append(f'<ul class="jd-list">{items}</ul>')
            bullet_buffer = []
    
    for line in lines:
        stripped = line.strip()
        
        # Empty line: in bullet state, skip (don't break bullet grouping)
        # In paragraph state, flush and reset
        if not stripped:
            if state == 'bullets':
                # Don't flush or reset — empty lines between bullets are common
                continue
            elif state == 'para':
                flush_para()
            continue
        
        # Section header: flush everything, emit header, expect bullets next
        if is_section_header(stripped):
            flush_para()
            flush_bullets()
            header_text = html_mod.escape(stripped.rstrip(':'))
            html_parts.append(f'<h3 class="jd-section-header">{header_text}</h3>')
            state = 'bullets'  # Headers typically precede bullet lists
            continue
        
        # Inline header (header + content on same line): emit header, treat rest as first bullet
        inline_header, rest = find_inline_header(line)
        if inline_header:
            flush_para()
            flush_bullets()
            header_text = html_mod.escape(inline_header.rstrip(':'))
            html_parts.append(f'<h3 class="jd-section-header">{header_text}</h3>')
            state = 'bullets'
            bullet_buffer.append(rest)
            continue
        
        # Explicit bullet character
        is_bul, bullet_char, rest = is_explicit_bullet(line)
        if is_bul:
            if state != 'bullets':
                flush_para()
                state = 'bullets'
            bullet_buffer.append(rest)
            continue
        
        # In bullet state: if line is a continuation/substantive line, keep as bullet item
        if state == 'bullets' and is_likely_content_line(stripped):
            # Check if it's actually a new paragraph (long, no bullet traits)
            if len(stripped) > 80 and not line.startswith(' ') and not any(
                stripped.lower().startswith(w) for w in ['carry', 'prepar', 'assist', 'attend', 'collab', 'ensure',
                    'support', 'provide', 'review', 'manage', 'develop', 'perform', 'conduct', 'coordinate',
                    'monitor', 'handle', 'maintain', 'implement', 'deliver', 'responsible', 'liaise', 'oversee']
            ):
                # This looks like a standalone paragraph, not a bullet continuation
                flush_bullets()
                state = 'para'
                para_buffer.append(stripped)
            else:
                # Treat as bullet item (implied or continuation)
                bullet_buffer.append(stripped)
            continue
        
        # Regular paragraph line
        if state != 'para':
            flush_bullets()
            state = 'para'
        para_buffer.append(stripped)
    
    # Flush remaining buffers
    flush_bullets()
    flush_para()
    
    return '\n'.join(html_parts)


def _format_inline(text: str) -> str:
    """Apply inline formatting within text that's already HTML-escaped."""
    # Bold ALL CAPS phrases (3+ uppercase words)
    text = re.sub(
        r'\b([A-Z][A-Z\s&]{4,}(?:\s[A-Z][A-Z\s&]{2,})*)\b',
        lambda m: f'<strong>{m.group(1)}</strong>' if m.group(1).strip().count(' ') >= 1 else m.group(1),
        text
    )
    return text


def convert_description(plain_text: str) -> str:
    """Convert a plain-text job description to structured HTML."""
    return format_plain_to_html(plain_text)


if __name__ == '__main__':
    import sys
    if len(sys.argv) > 1:
        text = sys.argv[1]
    else:
        text = sys.stdin.read()
    print(convert_description(text))
