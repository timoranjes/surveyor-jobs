# Render Migration — Setup Guide

## What this does

Migrates the Surveyor Job Dashboard backend from the local VPS to **Render (free plan)**, with **zero downtime** for the user. The friend keeps using `https://surveyor-jobs.11223344.best` — the only thing that changes is what's running on the other side of the Cloudflare Tunnel.

## How it works

```
[friend's browser] → https://surveyor-jobs.11223344.best
                              ↓
                     [Cloudflare Tunnel]
                              ↓
              [Backend — was VPS, now Render]
```

The tunnel URL stays the same. The backend is swapped behind it.

## What's in this repo (already done)

- ✅ `render.yaml` — Render service config (Python 3.11, free plan, no card)
- ✅ `scripts/seed_data.sql` — full SQLite data dump (161 jobs, 30 company profiles, etc.)
- ✅ `backend/database.py` — auto-restores from seed dump on first boot of each Render container
- ✅ Code is on GitHub: `https://github.com/timoranjes/surveyor-jobs`

## Two-step setup (~15 min total)

### Step 1: Create the Render service

1. Sign up for Render (free, no credit card): https://render.com/register
2. Generate an API key: https://dashboard.render.com/u/settings#api-keys
3. On the VPS, run:
   ```bash
   cd /home/orange/projects/surveyor-job-dashboard
   ./scripts/setup_render.sh
   ```
4. Paste the API key when prompted. The script creates the service and starts the first deploy.

The first build takes 3-5 minutes (pip install + start uvicorn). The service wakes up and seeds 161 jobs from the SQL dump.

### Step 2: Switch the tunnel

Once the Render service responds (check the dashboard), run:
```bash
cd /home/orange/projects/surveyor-job-dashboard
./scripts/switch_to_render.sh
```

This updates the named Cloudflare Tunnel to point at Render instead of `localhost:8765`. The friend's URL doesn't change.

**Verify the swap worked** by hitting the friend's URL:
```bash
curl -s -o /dev/null -w "%{http_code}\n" https://surveyor-jobs.11223344.best/api/analytics
# Should print 200
```

If it works, you can kill the local backend:
```bash
pkill -f "uvicorn backend.main:app"
```

## Data persistence on Render

Render's free plan has **no persistent disk**. The SQLite database lives in `/tmp/jobs.db` inside the container, which is reset when the container is recycled (after 15 min of inactivity).

**What survives across restarts:**
- ✅ The 161 jobs (re-seeded automatically from `seed_data.sql`)
- ✅ All company profiles, salary benchmarks, grad schemes
- ✅ CV data, match results (re-seeded)

**What does NOT survive:**
- ❌ New applications the friend added
- ❌ Status changes to applications (saved/applied/interview)

**Workaround:** For now, accept this. The friend is browsing jobs, not actively applying through this app. If active applications become important, we'll either:
- (a) Switch to Render's free Postgres (30-day expiry) — needs DB refactor
- (b) Use Neon free Postgres (no expiry) — needs DB refactor
- (c) Upgrade to a Render paid plan ($7/mo) which includes a persistent disk

## Free tier caveats

- **Sleep after 15 min idle**: First request after sleep takes 30-50 sec (cold start). The friend will see a delay if they don't use it for 15 min.
- **750 hours/month**: Enough for 24/7 (24 × 30 = 720 hrs).
- **Cold starts**: The auto-seed runs on every cold start, so the friend always sees the latest snapshot of jobs.

## Rollback

If something goes wrong and you need to go back to the VPS:
```bash
cd /home/orange/projects/surveyor-job-dashboard
# Restore the tunnel config backup
ls -la ~/.cloudflared/surveyor-jobs.yml.bak.*
cp ~/.cloudflared/surveyor-jobs.yml.bak.<latest> ~/.cloudflared/surveyor-jobs.yml
pkill -f "cloudflared tunnel run"
nohup cloudflared tunnel run surveyor-jobs &
# Restart the local backend
nohup ./run.sh &
```

## Files changed in this migration

| File | What changed |
|------|-------------|
| `render.yaml` | New: Render deployment config |
| `backend/database.py` | Reads `DB_PATH` env var, auto-restores from `seed_data.sql` on fresh boot |
| `backend/services/llm.py` | `LLM_LOG_DIR` env var (defaults to `backend/logs/`) |
| `backend/seed_graduate_schemes.py` | Honors `DB_PATH` env var |
| `scrapers/scraper.py` | Honors `DB_PATH` env var |
| `scripts/seed_data.sql` | New: full data dump (committed to repo) |
| `scripts/setup_render.sh` | New: creates Render service via API |
| `scripts/switch_to_render.sh` | New: switches tunnel to Render |
