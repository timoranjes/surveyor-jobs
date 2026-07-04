#!/usr/bin/env python3
"""
Smoke test suite for Surveyor Job Dashboard.
Run: python3 tests/smoke_test.py
Hits every endpoint, checks HTTP 200 + expected response shape.
Fails fast on regression — catches "route broke after a patch."
"""

import subprocess
import json
import sys
import time

BASE = "http://localhost:8765"
PASS = 0
FAIL = 0

def test(name, method, path, expected_status=200, data=None, checks=None):
    global PASS, FAIL
    try:
        if method == "GET":
            cmd = ["curl", "-s", "-w", "\n%{http_code}", f"{BASE}{path}"]
        else:
            cmd = ["curl", "-s", "-w", "\n%{http_code}", "-X", method, f"{BASE}{path}",
                   "-H", "Content-Type: application/json"]
            if data:
                cmd.extend(["-d", json.dumps(data)])

        out = subprocess.check_output(cmd, timeout=60).decode()
        lines = out.strip().split("\n")
        status = int(lines[-1])
        body = "\n".join(lines[:-1])

        if status != expected_status:
            print(f"  ❌ {name}: expected {expected_status}, got {status}")
            print(f"     {body[:200]}")
            FAIL += 1
            return False, body, status

        if checks:
            try:
                parsed = json.loads(body)
            except json.JSONDecodeError:
                print(f"  ❌ {name}: response is not valid JSON")
                FAIL += 1
                return False, body, status

            for check_name, check_fn in checks.items():
                try:
                    result = check_fn(parsed)
                    if result is not True:
                        print(f"  ❌ {name}/{check_name}: {result}")
                        FAIL += 1
                        return False, body, status
                except Exception as e:
                    print(f"  ❌ {name}/{check_name}: exception — {e}")
                    FAIL += 1
                    return False, body, status

        print(f"  ✅ {name}")
        PASS += 1
        return True, body, status

    except subprocess.TimeoutExpired:
        print(f"  ❌ {name}: timeout after 60s")
        FAIL += 1
        return False, "", 0
    except Exception as e:
        print(f"  ❌ {name}: {e}")
        FAIL += 1
        return False, "", 0


def has_key(key):
    return lambda d: True if key in d else f"missing key '{key}'"

def non_empty_list(key):
    return lambda d: True if isinstance(d.get(key), list) else f"'{key}' is not a list"

def non_zero(key):
    return lambda d: True if d.get(key, 0) > 0 else f"'{key}' is zero or missing"

def is_list():
    return lambda d: True if isinstance(d, list) else f"not a list"


print("=" * 60)
print("SURVEYOR JOB DASHBOARD — SMOKE TEST")
print("=" * 60)

# === Jobs ===
test("GET /api/jobs", "GET", "/api/jobs?limit=2",
     checks={"has_total": non_zero("total"), "has_jobs": non_empty_list("jobs")})

test("GET /api/jobs (discipline filter)", "GET", "/api/jobs?discipline=quantity_surveying&limit=1",
     checks={"has_total": has_key("total")})

test("GET /api/jobs (experience filter)", "GET", "/api/jobs?experience_level=graduate&limit=1",
     checks={"has_total": has_key("total")})

test("GET /api/jobs (search)", "GET", "/api/jobs?search=surveyor&limit=1",
     checks={"has_total": has_key("total")})

test("GET /api/jobs/ranked", "GET", "/api/jobs/ranked?limit=3",
     checks={"has_jobs": non_empty_list("jobs")})

# Get a real job_id for detail test
ok, body, _ = test("GET /api/jobs (get first ID)", "GET", "/api/jobs?limit=1",
                    checks={"has_jobs": non_empty_list("jobs")})
job_id = None
if ok:
    jobs = json.loads(body)["jobs"]
    if jobs:
        job_id = jobs[0]["id"]

if job_id:
    test(f"GET /api/jobs/{job_id}", "GET", f"/api/jobs/{job_id}",
         checks={"has_title": has_key("title"), "has_company": has_key("company")})

# === Applications ===
test("GET /api/applications", "GET", "/api/applications",
     checks={"has_applications": has_key("applications")})

if job_id:
    test(f"POST /api/applications/{job_id}", "POST", f"/api/applications/{job_id}",
         data={"status": "saved"},
         checks={"has_id": has_key("id")})

    # Get app ID for update/delete test
    ok2, body2, _ = test("GET /api/applications (after create)", "GET", "/api/applications",
                          checks={"has_applications": has_key("applications")})
    if ok2:
        apps = json.loads(body2).get("applications", [])
        if apps:
            app_id = apps[0]["id"]
            test(f"PATCH /api/applications/id/{app_id}", "PATCH", f"/api/applications/id/{app_id}",
                 data={"status": "applied", "pipeline_stage": "applied"},
                 checks={"has_status": has_key("status")})

            test(f"DELETE /api/applications/{job_id}", "DELETE", f"/api/applications/{job_id}",
                 checks={"has_ok": has_key("ok")})

# === CV ===
test("GET /api/cv", "GET", "/api/cv",
     checks={"has_full_text": has_key("full_text")})

# === CV Match ===
test("POST /api/cv/match-all (no-op)", "POST", "/api/cv/match-all",
     checks={"has_matched": has_key("matched")})

# === Company Research ===
test("GET /api/companies/AECOM", "GET", "/api/companies/AECOM",
     checks={"has_overview": has_key("overview")})

# === Graduate Schemes ===
test("GET /api/graduate-schemes", "GET", "/api/graduate-schemes",
     checks={"has_schemes": non_empty_list("schemes")})

test("GET /api/graduate-schemes/stats", "GET", "/api/graduate-schemes/stats",
     checks={"has_total": non_zero("total")})

# === Pipeline ===
test("GET /api/pipeline", "GET", "/api/pipeline",
     checks={"has_stages": has_key("stages")})

test("GET /api/pipeline/stats", "GET", "/api/pipeline/stats",
     checks={"has_summary": has_key("summary")})

# === Salary Benchmarks ===
test("GET /api/salary-benchmarks", "GET", "/api/salary-benchmarks",
     checks={"has_benchmarks": has_key("benchmarks")})

# === Analytics ===
test("GET /api/analytics", "GET", "/api/analytics",
     checks={"has_total_jobs": non_zero("total_jobs")})

# === Static files ===
test("GET / (index.html)", "GET", "/", expected_status=200)
test("GET /style.css", "GET", "/style.css", expected_status=200)
test("GET /app.js", "GET", "/app.js", expected_status=200)

print("\n" + "=" * 60)
print(f"RESULTS: {PASS} passed, {FAIL} failed, {PASS + FAIL} total")
print("=" * 60)

if FAIL > 0:
    print("\n⚠️  SOME TESTS FAILED — check output above for details.")
    sys.exit(1)
else:
    print("\n✅ All smoke tests passed.")
    sys.exit(0)
