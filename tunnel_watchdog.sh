#!/bin/bash
# Check if the surveyor dashboard tunnel is alive.
# If not, restart it. Run via cron every 5 min.
URL_FILE="/home/orange/projects/surveyor-job-dashboard/.tunnel_url"
PID_FILE="/tmp/tunnel_watchdog.pid"

# Check if backend is up
if ! curl -sf http://localhost:8765/api/jobs > /dev/null 2>&1; then
    echo "[$(date)] Backend down, restarting..."
    cd /home/orange/projects/surveyor-job-dashboard
    nohup python3 -m uvicorn backend.main:app --host 127.0.0.1 --port 8765 > /tmp/uvicorn_surveyor.log 2>&1 &
    sleep 2
fi

# Check if tunnel is up
TUNNEL_URL=$(cat "$URL_FILE" 2>/dev/null)
if [ -n "$TUNNEL_URL" ]; then
    if curl -sf "$TUNNEL_URL/api/jobs" > /dev/null 2>&1; then
        # Tunnel is healthy
        exit 0
    fi
fi

# Tunnel is down — restart
echo "[$(date)] Tunnel down, restarting..."
pkill -f "cloudflared tunnel --url" 2>/dev/null || true
sleep 1
nohup bash /home/orange/projects/surveyor-job-dashboard/start_tunnel_persistent.sh > /dev/null 2>&1 &
