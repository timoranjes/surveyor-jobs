#!/bin/bash
# ==============================================================
# Surveyor Job Dashboard — Persistent Tunnel Launcher
# ==============================================================
# Runs cloudflared tunnel for the surveyor dashboard.
# On restart (new URL), updates both the .tunnel_url file
# and notifies via Discord so you always know the current URL.
#
# Usage: ./start_tunnel_persistent.sh
# ==============================================================

set -e

CF_BIN="/tmp/cloudflared"
BACKEND_PORT="8765"
PROJECT_DIR="/home/orange/projects/surveyor-job-dashboard"
URL_FILE="$PROJECT_DIR/.tunnel_url"
LOG_FILE="$PROJECT_DIR/tunnel.log"

# Kill any existing tunnel
pkill -f "$CF_BIN tunnel --url" 2>/dev/null || true
sleep 1

echo "[$(date '+%Y-%m-%d %H:%M:%S')] Starting tunnel..." | tee -a "$LOG_FILE"

# Start tunnel in background, capture URL
$CF_BIN tunnel --url "http://localhost:$BACKEND_PORT" --no-autoupdate \
    --loglevel info 2>&1 | while IFS= read -r line; do
    echo "$line" >> "$LOG_FILE"
    
    # Extract the trycloudflare URL when it appears
    if [[ "$line" =~ (https://[a-zA-Z0-9.-]+\.trycloudflare\.com) ]]; then
        URL="${BASH_REMATCH[1]}"
        echo "$URL" > "$URL_FILE"
        echo "[$(date '+%Y-%m-%d %H:%M:%S')] TUNNEL LIVE: $URL" | tee -a "$LOG_FILE"
        
        # Write an easy-to-read status file
        cat > "$PROJECT_DIR/.tunnel_status.json" << JSONEOF
{
    "url": "$URL",
    "started_at": "$(date -Iseconds)",
    "port": $BACKEND_PORT
}
JSONEOF
    fi
done
