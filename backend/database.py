"""
SQLite database schema and connection manager.
Tables: jobs, applications, cv_analyses, salary_benchmarks, company_profiles
"""

import sqlite3
import os
from datetime import datetime

# DB_PATH can be overridden by env var (for Render persistent disk: /var/data/jobs.db)
_DB_ENV = os.environ.get("DB_PATH")
if _DB_ENV:
    DB_PATH = _DB_ENV
    # Ensure parent dir exists
    os.makedirs(os.path.dirname(DB_PATH) or ".", exist_ok=True)
else:
    DB_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "jobs.db")


def get_db() -> sqlite3.Connection:
    """Get database connection with row factory."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db():
    """Initialize all tables. Also auto-restores from scripts/seed_data.sql
    on first run (e.g. fresh Render deploy) if the DB is empty."""
    os.makedirs(os.path.dirname(DB_PATH) or ".", exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.executescript("""
        CREATE TABLE IF NOT EXISTS jobs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            external_id TEXT UNIQUE,
            title TEXT NOT NULL,
            company TEXT NOT NULL,
            discipline TEXT NOT NULL CHECK(discipline IN ('quantity_surveying','land_surveying','building_surveying','general_practice','planning','other')),
            location TEXT DEFAULT 'Hong Kong',
            salary_range TEXT,
            description TEXT,
            description_html TEXT,
            requirements TEXT,
            url TEXT,
            source TEXT,
            posted_date TEXT,
            closing_date TEXT,
            fresh_grad_friendly INTEGER DEFAULT 1,
            experience_level TEXT DEFAULT 'entry',
            created_at TEXT DEFAULT (datetime('now')),
            updated_at TEXT DEFAULT (datetime('now')),
            is_active INTEGER DEFAULT 1,
            last_seen_scrape INTEGER DEFAULT 0
        );

        CREATE TABLE IF NOT EXISTS applications (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            job_id INTEGER NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
            status TEXT NOT NULL DEFAULT 'saved' CHECK(status IN ('saved','applied','interview','offer','accepted','rejected','withdrawn')),
            applied_date TEXT,
            notes TEXT,
            cover_letter TEXT,
            follow_up_date TEXT,
            created_at TEXT DEFAULT (datetime('now')),
            updated_at TEXT DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS cv_data (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            full_text TEXT NOT NULL,
            parsed_sections TEXT,
            key_skills TEXT,
            education TEXT,
            experience_summary TEXT,
            created_at TEXT DEFAULT (datetime('now')),
            updated_at TEXT DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS cv_match_results (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            job_id INTEGER NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
            cv_id INTEGER NOT NULL REFERENCES cv_data(id) ON DELETE CASCADE,
            match_score REAL,
            strengths TEXT,
            gaps TEXT,
            suggestions TEXT,
            tailored_cv TEXT,
            cover_letter TEXT,
            interview_questions TEXT,
            created_at TEXT DEFAULT (datetime('now')),
            hard_requirements_match TEXT,
            soft_requirements_match TEXT,
            UNIQUE(job_id, cv_id)
        );

        CREATE TABLE IF NOT EXISTS company_profiles (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            company_name TEXT UNIQUE NOT NULL,
            overview TEXT,
            hk_projects TEXT,
            reputation_notes TEXT,
            glassdoor_rating REAL,
            employee_count TEXT,
            founded_year TEXT,
            headquarters TEXT,
            recent_news TEXT,
            hk_government_contracts TEXT,
            glassdoor_review_count INTEGER,
            glassdoor_pros TEXT,
            glassdoor_cons TEXT,
            apc_training INTEGER,
            apc_training_details TEXT,
            staff_turnover_notes TEXT,
            interview_tips TEXT,
            competitor_comparison TEXT,
            typical_graduate_salary TEXT,
            graduate_program_details TEXT,
            last_researched TEXT,
            created_at TEXT DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS salary_benchmarks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            discipline TEXT NOT NULL,
            experience_level TEXT NOT NULL,
            percentile_25 REAL,
            percentile_50 REAL,
            percentile_75 REAL,
            source TEXT,
            updated_at TEXT DEFAULT (datetime('now')),
            UNIQUE(discipline, experience_level)
        );

        CREATE TABLE IF NOT EXISTS skill_gap_analysis (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            cv_id INTEGER NOT NULL REFERENCES cv_data(id) ON DELETE CASCADE,
            missing_skills TEXT,
            recommended_courses TEXT,
            created_at TEXT DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS graduate_schemes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            company_name TEXT NOT NULL,
            scheme_name TEXT NOT NULL,
            discipline TEXT,
            application_open TEXT,
            application_close TEXT,
            intake_year TEXT,
            url TEXT,
            notes TEXT,
            is_active INTEGER DEFAULT 1
        );

        CREATE TABLE IF NOT EXISTS scrape_counter (
            id INTEGER PRIMARY KEY CHECK(id=1),
            counter INTEGER DEFAULT 0
        );

        CREATE INDEX IF NOT EXISTS idx_jobs_discipline ON jobs(discipline);
        CREATE INDEX IF NOT EXISTS idx_jobs_fresh_grad ON jobs(fresh_grad_friendly);
        CREATE INDEX IF NOT EXISTS idx_jobs_company ON jobs(company);
        CREATE INDEX IF NOT EXISTS idx_applications_job ON applications(job_id);
        CREATE INDEX IF NOT EXISTS idx_applications_status ON applications(status);
        CREATE INDEX IF NOT EXISTS idx_match_job_cv ON cv_match_results(job_id, cv_id);
        CREATE INDEX IF NOT EXISTS idx_grad_schemes_close ON graduate_schemes(application_close);
    """)

    # Seed salary benchmarks for HK surveying
    cursor.execute("SELECT COUNT(*) FROM salary_benchmarks")
    if cursor.fetchone()[0] == 0:
        cursor.executemany(
            "INSERT INTO salary_benchmarks (discipline, experience_level, percentile_25, percentile_50, percentile_75, source) VALUES (?,?,?,?,?,?)",
            [
                ("quantity_surveying", "entry", 18000, 22000, 28000, "HK market data 2026"),
                ("quantity_surveying", "graduate", 16000, 20000, 25000, "HK market data 2026"),
                ("land_surveying", "entry", 20000, 25000, 32000, "HK market data 2026"),
                ("land_surveying", "graduate", 18000, 22000, 28000, "HK market data 2026"),
                ("building_surveying", "entry", 18000, 23000, 30000, "HK market data 2026"),
                ("building_surveying", "graduate", 16000, 21000, 26000, "HK market data 2026"),
                ("general_practice", "entry", 17000, 22000, 28000, "HK market data 2026"),
                ("general_practice", "graduate", 15000, 19000, 24000, "HK market data 2026"),
            ],
        )

    conn.commit()
    conn.close()
    print(f"Database initialized at {DB_PATH}")

    # === Step 1: auto-restore from seed dump if this was a fresh DB ===
    # (must happen before any seeding that depends on the dump not having data)
    # Skip on subsequent boots if jobs already exist.
    try:
        check = sqlite3.connect(DB_PATH)
        job_count = check.execute("SELECT COUNT(*) FROM jobs").fetchone()[0]
        check.close()
        if job_count == 0:
            candidates = [
                os.path.join(os.path.dirname(__file__), "..", "scripts", "seed_data.sql"),
                os.path.join(os.getcwd(), "scripts", "seed_data.sql"),
                os.path.join(os.getcwd(), "..", "scripts", "seed_data.sql"),
            ]
            for seed_path in candidates:
                seed_path = os.path.abspath(seed_path)
                if os.path.exists(seed_path):
                    print(f"Empty DB detected, restoring from {seed_path}...")
                    seed_conn = sqlite3.connect(DB_PATH)
                    seed_conn.execute("PRAGMA journal_mode=WAL")
                    with open(seed_path) as f:
                        sql_script = f.read()
                    # The dump uses INSERT OR REPLACE so it's idempotent and
                    # tolerates partial prior state.
                    seed_conn.executescript(sql_script)
                    seed_conn.commit()
                    seed_conn.close()
                    after = sqlite3.connect(DB_PATH).execute("SELECT COUNT(*) FROM jobs").fetchone()[0]
                    print(f"  -> Restored {after} jobs from seed data")
                    break
    except Exception as e:
        print(f"Note: seed data restore skipped ({e})")

    # === Step 2: post-restore housekeeping ===
    # (No further re-seeding: the seed restore above only runs if the DB is
    # empty. New data within a session is preserved as long as the container
    # is alive. Render free tier recycles the container after 15min idle,
    # which wipes any new interactions — acceptable for browse-only use.)

    # Seed graduate schemes on first init
    try:
        from backend.seed_graduate_schemes import seed
        seed()
    except Exception as e:
        print(f"Note: graduate scheme seeding skipped ({e})")

    # Ensure scrape_counter exists (used by scraper staleness pruning)
    try:
        c = sqlite3.connect(DB_PATH)
        c.execute("CREATE TABLE IF NOT EXISTS scrape_counter (id INTEGER PRIMARY KEY CHECK(id=1), counter INTEGER DEFAULT 0)")
        c.execute("INSERT OR IGNORE INTO scrape_counter (id, counter) VALUES (1, 0)")
        c.commit()
        c.close()
    except Exception:
        pass


if __name__ == "__main__":
    init_db()
