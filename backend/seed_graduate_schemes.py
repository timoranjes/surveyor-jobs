"""Seed graduate schemes for HK surveying 2026/2027 intake."""

import sqlite3
import os

DB_PATH = os.environ.get("DB_PATH") or os.path.join(os.path.dirname(__file__), "..", "data", "jobs.db")

SCHEMES = [
    {
        "company_name": "AECOM",
        "scheme_name": "Graduate Programme (QS, BS, LS)",
        "discipline": "multiple",
        "application_open": "2026-09-01",
        "application_close": "2026-11-30",
        "intake_year": "2027",
        "url": "https://aecom.com/hk/careers/",
        "notes": "One of the largest engineering consultancies. Multiple surveying disciplines available. Typically hires graduates for QS, Building Surveying, and Land Surveying streams.",
    },
    {
        "company_name": "Arcadis",
        "scheme_name": "Graduate Programme (QS, BS)",
        "discipline": "multiple",
        "application_open": "2026-09-01",
        "application_close": "2026-11-15",
        "intake_year": "2027",
        "url": "https://www.arcadis.com/en-hk/careers",
        "notes": "Global consultancy — strong in QS and building surveying. Graduate programme includes structured training and mentorship.",
    },
    {
        "company_name": "Rider Levett Bucknall (RLB)",
        "scheme_name": "Graduate Quantity Surveyor Intake",
        "discipline": "quantity_surveying",
        "application_open": "2026-10-01",
        "application_close": "2027-01-31",
        "intake_year": "2027",
        "url": "https://www.rlb.com/asiapacific/careers/",
        "notes": "Major international cost consultancy. Structured graduate programme with APC support. Strong HK presence.",
    },
    {
        "company_name": "Langdon & Seah",
        "scheme_name": "Graduate Quantity Surveyor",
        "discipline": "quantity_surveying",
        "application_open": "2026-09-15",
        "application_close": "2026-12-31",
        "intake_year": "2027",
        "url": "https://www.langdonseah.com/careers",
        "notes": "Well-established QS practice in HK. Known for good training culture. Part of Arcadis group.",
    },
    {
        "company_name": "C M Wong & Associates",
        "scheme_name": "Graduate Quantity Surveyor",
        "discipline": "quantity_surveying",
        "application_open": "2026-10-01",
        "application_close": "TBC",
        "intake_year": "2027",
        "url": "",
        "notes": "Local HK QS firm. Accepts applications year-round — contact directly.",
    },
    {
        "company_name": "Currie & Brown",
        "scheme_name": "Graduate Quantity Surveyor",
        "discipline": "quantity_surveying",
        "application_open": "2026-09-01",
        "application_close": "2026-12-31",
        "intake_year": "2027",
        "url": "https://www.curriebrown.com/en-hk/careers",
        "notes": "International construction consultancy. Graduate programme with APC/RICS pathway.",
    },
    {
        "company_name": "Turner & Townsend",
        "scheme_name": "Graduate Programme",
        "discipline": "quantity_surveying",
        "application_open": "2026-09-01",
        "application_close": "2026-11-30",
        "intake_year": "2027",
        "url": "https://www.turnerandtownsend.com/en/locations/asia/hong-kong/",
        "notes": "Global professional services firm. Strong QS and project management graduate intake in HK.",
    },
    {
        "company_name": "WT Partnership",
        "scheme_name": "Graduate Quantity Surveyor",
        "discipline": "quantity_surveying",
        "application_open": "2026-09-01",
        "application_close": "2026-12-15",
        "intake_year": "2027",
        "url": "https://www.wtpartnership.com/careers/",
        "notes": "International cost consultancy. Good graduate training with APC mentoring.",
    },
    {
        "company_name": "Faithful+Gould (Surbana Jurong)",
        "scheme_name": "Graduate Programme",
        "discipline": "quantity_surveying",
        "application_open": "2026-09-15",
        "application_close": "2026-12-01",
        "intake_year": "2027",
        "url": "https://surbanajurong.com/careers/",
        "notes": "Now part of Surbana Jurong Group. Graduate programme covers QS and project management disciplines.",
    },
    {
        "company_name": "Leighton Asia",
        "scheme_name": "Graduate Engineer (Surveying-adjacent)",
        "discipline": "other",
        "application_open": "2026-09-01",
        "application_close": "2026-11-30",
        "intake_year": "2027",
        "url": "https://www.leightonasia.com/en/careers/graduate-program/",
        "notes": "Major contractor. Graduate programme may include surveying-adjacent roles. Worth checking for QS/contracts positions.",
    },
    {
        "company_name": "Gammon Construction",
        "scheme_name": "Graduate Trainee (QS)",
        "discipline": "quantity_surveying",
        "application_open": "2026-10-01",
        "application_close": "2027-02-28",
        "intake_year": "2027",
        "url": "https://www.gammonconstruction.com/en/html/careers/graduate-trainees.html",
        "notes": "Major HK contractor. Graduate trainee programme includes QS stream. Well-structured training with good progression.",
    },
    {
        "company_name": "Housing Authority / Housing Department",
        "scheme_name": "Graduate Surveyor",
        "discipline": "multiple",
        "application_open": "2026-09-01",
        "application_close": "TBC",
        "intake_year": "2027",
        "url": "https://www.housingauthority.gov.hk/en/about-us/careers/",
        "notes": "Government position. Check Civil Service Bureau recruitment page. Typically through government-wide graduate recruitment exercise.",
    },
    {
        "company_name": "Architectural Services Department (ArchSD)",
        "scheme_name": "Graduate Surveyor",
        "discipline": "multiple",
        "application_open": "2026-09-01",
        "application_close": "TBC",
        "intake_year": "2027",
        "url": "https://www.archsd.gov.hk/en/careers/",
        "notes": "Government department managing public building projects. Hires graduate surveyors across QS, BS, and LS disciplines.",
    },
    {
        "company_name": "Lands Department",
        "scheme_name": "Graduate Surveyor",
        "discipline": "land_surveying",
        "application_open": "2026-09-01",
        "application_close": "TBC",
        "intake_year": "2027",
        "url": "https://www.landsd.gov.hk/en/about-us/careers.html",
        "notes": "Government department — primary employer of land surveyors in HK. Check Civil Service Bureau for recruitment rounds.",
    },
    {
        "company_name": "Buildings Department",
        "scheme_name": "Graduate Surveyor",
        "discipline": "building_surveying",
        "application_open": "2026-09-01",
        "application_close": "TBC",
        "intake_year": "2027",
        "url": "https://www.bd.gov.hk/en/about-us/recruitment/",
        "notes": "Government department. Heavy focus on building surveying. Check government recruitment portal for exact dates.",
    },
    {
        "company_name": "MTR Corporation",
        "scheme_name": "Graduate Surveyor",
        "discipline": "multiple",
        "application_open": "2026-09-01",
        "application_close": "2026-12-31",
        "intake_year": "2027",
        "url": "https://www.mtr.com.hk/en/corporate/careers/graduate_trainee.html",
        "notes": "MTR's graduate trainee programme includes surveying roles in property and projects divisions. Highly competitive but excellent career pathway.",
    },
]


def seed():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # Check if already seeded
    count = cursor.execute("SELECT COUNT(*) FROM graduate_schemes").fetchone()[0]
    if count > 0:
        print(f"Graduate schemes already seeded ({count} existing). Skipping.")
        conn.close()
        return

    cursor.executemany(
        """INSERT INTO graduate_schemes
           (company_name, scheme_name, discipline, application_open, application_close, intake_year, url, notes)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        [
            (
                s["company_name"], s["scheme_name"], s["discipline"],
                s["application_open"], s["application_close"], s["intake_year"],
                s["url"], s["notes"],
            )
            for s in SCHEMES
        ],
    )
    conn.commit()
    conn.close()
    print(f"Seeded {len(SCHEMES)} graduate schemes.")


if __name__ == "__main__":
    seed()
