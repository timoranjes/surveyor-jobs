#!/bin/bash
# Persistent Cloudflare Tunnel launcher for Surveyor Job Dashboard
# Runs the tunnel and writes the URL to a fixed file so crons/scripts can find it.

CF_BIN="/tmp/cloudflared"
BACKEND_PORT="8765"
URL_FILE="/home/orange/projects/surveyor-job-dashboard/.tunnel_url"

# Kill any existing tunnel
pkill -f "$CF_BIN tunnel --url" 2>/dev/null
sleep 1

# Start tunnel, capture URL from stderr
$CF_BIN tunnel --url http://localhost:$BACKEND_PORT --no-autoupdate 2>&1 | while read line; do
    echo "$line"
    # Extract the trycloudflare URL when it appears
    if [[ "$line" =~ https://[^ ]+trycloudflare\.com ]]; then
        URL=$(echo "$line" | grep -o 'https://[^ ]*trycloudflare\.com' | head -1)
        echo "$URL" > "$URL_FILE"
        echo "TUNNEL_URL=$URL"
    fi
done
