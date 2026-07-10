#!/bin/bash
# ==============================================================
# Switch Cloudflare Tunnel to Render
# ==============================================================
# This script updates the named Cloudflare tunnel so that
# surveyor-jobs.11223344.best points at the Render service
# instead of the local VPS. The friend's URL does NOT change.
#
# Run AFTER ./setup_render.sh has completed and the Render
# service is responding 200 OK.
# ==============================================================

set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

CF_BIN="cloudflared"
CF_CONFIG_DIR="$HOME/.cloudflared"
CF_CONFIG="$CF_CONFIG_DIR/surveyor-jobs.yml"
TUNNEL_NAME="surveyor-jobs"

echo ""
echo "${YELLOW}═══════════════════════════════════════════════════════${NC}"
echo "${YELLOW}  Switch tunnel to Render${NC}"
echo "${YELLOW}═══════════════════════════════════════════════════════${NC}"
echo ""

# --- 1. Get Render URL ---
read -p "Paste your Render service URL (e.g. https://surveyor-jobs-xxxx.onrender.com): " RENDER_URL
RENDER_URL=$(echo "$RENDER_URL" | sed 's:/*$::')  # strip trailing slash
if [ -z "$RENDER_URL" ]; then
    echo "${RED}ERROR: Render URL required${NC}"
    exit 1
fi

# Validate
if [[ ! "$RENDER_URL" =~ ^https://.*\.onrender\.com$ ]]; then
    echo "${YELLOW}WARNING: URL doesn't look like a Render URL. Continue anyway? [y/N]${NC}"
    read -p "" CONFIRM
    if [[ ! "$CONFIRM" =~ ^[Yy]$ ]]; then
        exit 1
    fi
fi

# --- 2. Test the Render URL is alive ---
echo ""
echo -n "  Testing Render URL... "
HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" --max-time 15 "$RENDER_URL/" || echo "000")
if [ "$HTTP_CODE" != "200" ]; then
    echo "${RED}FAILED (HTTP $HTTP_CODE)${NC}"
    echo "  Render service not responding. Make sure it's deployed first."
    exit 1
fi
echo "${GREEN}OK (HTTP 200)${NC}"

# Test API too
echo -n "  Testing Render API... "
HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" --max-time 15 "$RENDER_URL/api/analytics" || echo "000")
if [ "$HTTP_CODE" != "200" ]; then
    echo "${RED}FAILED (HTTP $HTTP_CODE)${NC}"
    exit 1
fi
echo "${GREEN}OK${NC}"

# --- 3. Update tunnel config ---
echo ""
echo -n "  Backing up $CF_CONFIG... "
cp "$CF_CONFIG" "$CF_CONFIG.bak.$(date +%s)" 2>/dev/null && echo "OK" || echo "no backup needed"

echo "  Updating tunnel ingress to point at Render..."
cat > "$CF_CONFIG" <<EOF
tunnel: $(grep '^tunnel:' "$CF_CONFIG.bak."* 2>/dev/null | head -1 | awk '{print $2}')

ingress:
  - hostname: surveyor-jobs.11223344.best
    service: $RENDER_URL
  - service: http_status:404
EOF

# --- 4. Restart tunnel ---
echo ""
echo "  Restarting tunnel..."
pkill -f "cloudflared tunnel run" 2>/dev/null || true
sleep 2

nohup $CF_BIN tunnel run $TUNNEL_NAME > tunnel.log 2>&1 &
sleep 5

# --- 5. Verify ---
echo ""
echo -n "  Verifying tunnel through friend's URL... "
HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" --max-time 15 \
    https://surveyor-jobs.11223344.best/api/analytics || echo "000")

if [ "$HTTP_CODE" == "200" ]; then
    echo "${GREEN}OK (HTTP 200)${NC}"
else
    echo "${RED}FAILED (HTTP $HTTP_CODE)${NC}"
    echo "  Reverting config..."
    cp "$CF_CONFIG.bak."* "$CF_CONFIG" 2>/dev/null
    pkill -f "cloudflared tunnel run" 2>/dev/null
    nohup $CF_BIN tunnel run $TUNNEL_NAME > tunnel.log 2>&1 &
    exit 1
fi

echo ""
echo "${GREEN}═══════════════════════════════════════════════════════${NC}"
echo "${GREEN}  Done! ${NC}"
echo "${GREEN}═══════════════════════════════════════════════════════${NC}"
echo ""
echo "  Friend's URL: ${GREEN}https://surveyor-jobs.11223344.best${NC}"
echo "  Backend now:  ${GREEN}$RENDER_URL${NC}"
echo ""
echo "You can safely kill the local backend once you verify the above works:"
echo "  pkill -f 'uvicorn backend.main:app'"
echo ""
echo "The local SQLite data is preserved at: data/jobs.db"
echo ""
