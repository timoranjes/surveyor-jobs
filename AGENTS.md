# Surveyor Job Dashboard — AGENTS.md

## Purpose
A personal job-hunting dashboard for a junior surveyor fresh graduate in Hong Kong. Tracks open positions, application status, and provides AI-powered CV-to-job matching.

## Stack
- **Backend:** Python 3.11 + FastAPI + SQLite (sqlite3 stdlib)
- **Frontend:** Single-page HTML + vanilla JS + CSS (served by FastAPI)
- **AI:** DeepSeek V4 Flash API (deepseek provider, key in ~/.hermes/.env)
- **Scraping:** Google Jobs via SerpApi (primary) + HKIS board + LinkedIn fallback
- **Deploy:** Cloudflare Tunnel → surveyor-jobs.11223344.best

## Project Structure
```
surveyor-job-dashboard/
├── AGENTS.md
├── backend/
│   ├── main.py              # FastAPI entry point
│   ├── database.py          # SQLite schema + connection
│   ├── models.py            # Pydantic models
│   ├── routes/
│   │   ├── jobs.py          # Job CRUD + filtering (experience_level param)
│   │   ├── applications.py  # Application tracking
│   │   ├── cv.py            # CV upload + analysis + matching (debug support)
│   │   ├── companies.py     # Company research (debug support)
│   │   └── analytics.py     # Dashboard stats
│   ├── services/
│   │   ├── llm.py           # DeepSeek API client (HK-calibrated prompts)
│   │   ├── company_research.py  # SerpApi + LLM company research
│   │   └── file_parser.py   # PDF/DOCX CV extraction
│   └── requirements.txt
├── frontend/
│   ├── index.html           # SPA shell with debug toggle
│   ├── style.css            # Design system + debug panel styles
│   └── app.js               # All client-side logic (vanilla JS)
├── scrapers/
│   ├── scraper.py           # Main scraper orchestration (HKIS, LinkedIn, CTgoodjobs)
│   ├── google_jobs_scraper.py  # SerpApi Google Jobs (16 queries incl. Chinese)
│   ├── backfill_descriptions.py # Backfill HTML descriptions from source pages
│   ├── html_scraper.py      # Source page HTML fetcher
│   └── description_formatter.py  # Plain text → HTML formatter
├── data/
│   └── jobs.db              # SQLite database (gitignored)
├── run.sh                   # Start script (venv + uvicorn)
├── start_tunnel.sh          # Temporary Cloudflare Tunnel
├── start_tunnel_persistent.sh  # Named Cloudflare Tunnel
└── tunnel_watchdog.sh       # Tunnel health monitor
```

## Database Schema
- **jobs** — scraped listings: id, external_id, title, company, discipline, location, salary_range, description, description_html, requirements, url, source, posted_date, closing_date, fresh_grad_friendly, experience_level (graduate/entry/experienced), is_active
- **applications** — tracking: id, job_id, status, applied_date, notes, cover_letter, follow_up_date
- **cv_data** — stored CV + LLM analysis: full_text, key_skills, education, experience_summary, hkis_eligible, languages, certifications
- **cv_match_results** — per-job match: match_score, strengths, gaps, suggestions, tailored_cv, cover_letter, interview_questions
- **company_profiles** — LLM-researched: overview, hk_projects, hk_government_contracts, glassdoor_rating, interview_tips, apc_training, typical_graduate_salary, graduate_program_details
- **salary_benchmarks** — seeded HK market data by discipline + experience level
- **skill_gap_analysis** — cross-job gaps + recommended courses

## API Endpoints
| Method | Path | Purpose |
|--------|------|---------|
| GET | `/api/jobs` | List/filter jobs (experience_level, discipline, status, search, pagination) |
| GET | `/api/jobs/{id}` | Job detail + match data + application status |
| POST | `/api/jobs/scrape` | Trigger scrape (runs with --skip-backfill for fast manual refresh) |
| POST | `/api/jobs` | Create job (used by scrapers) |
| DELETE | `/api/jobs/{id}` | Soft-delete |
| GET | `/api/applications` | List applications with job details |
| POST | `/api/applications/{job_id}` | Create/upsert application |
| PATCH | `/api/applications/{id}` | Update status/notes |
| DELETE | `/api/applications/{job_id}` | Remove application (reset to Not Applied) |
| POST | `/api/cv/upload` | Save CV text (PDF/DOCX/TXT) |
| GET | `/api/cv` | Get stored CV |
| POST | `/api/cv/analyze?debug=true` | LLM CV analysis (HKIS-aware) |
| POST | `/api/cv/match/{job_id}?debug=true` | CV-to-job match + cover letter + interview questions |
| POST | `/api/cv/skill-gaps` | Cross-job skill gap analysis |
| GET | `/api/companies/{name}?debug=true` | LLM company research (cached 30 days) |
| GET | `/api/salary-benchmarks` | Salary data by discipline |
| GET | `/api/analytics` | Dashboard stats |

## Key Features (Post-July 2026 Audit)
- **3-tier experience filter** (graduate/entry/experienced) — replaces broken fresh_grad_only binary
- **Non-surveying job filter** — aggressive blacklist excludes solicitors, traders, engineers (unless surveying-adjacent)
- **Discipline auto-classification** — title-based mapping to QS/BS/LS/GP
- **HKIS board scraper** — official surveying institute job board
- **Chinese search queries** — 7 Chinese terms for broader coverage
- **Closing date extraction** — 11 regex patterns (EN/CN/ISO/abbreviated)
- **LLM debug panel** — toggle in nav shows raw prompts, responses, and parsed data
- **HK-calibrated LLM** — HKIS APC awareness, PolyU recognition, honest 6-band scoring (anti-inflation), HK salary bands, Cantonese requirement
- **Anti-fabrication rules** — LLM instructed to say "Unknown" rather than fabricate

## Conventions
- Python 3.11+, PEP 668 — use venv at /home/orange/projects/surveyor-job-dashboard/venv/
- All API responses JSON
- Frontend fetches from same-origin (backend serves static files)
- CSS/JS version strings bumped on changes (?v=11)
- Debug mode: opt-in via `?debug=true` on LLM endpoints or Debug toggle in UI

## Environment
- `DEEPSEEK_API_KEY` from `~/.hermes/.env`
- `SERPAPI_API_KEY` from `~/.hermes/.env` (for Google Jobs scraper)
- DeepSeek endpoint: `https://api.deepseek.com/v1/chat/completions`

## Known Issues
- 7 pre-existing non-surveying jobs remain in DB (filter only applies to new scrapes)
- Job board scraping is fragile (HTML structure changes)
- Single-user design (no auth) — fine for personal use
- Cloudflare Tunnel URL changes on restart (use start_tunnel_persistent.sh for named tunnel)
- Closing dates rarely present in job descriptions (1/100 extracted)
