#!/bin/bash
# ==============================================================
# Render Setup — One-time deployment for Surveyor Job Dashboard
# ==============================================================
# This script deploys the backend to Render (free plan) using the
# Render REST API. Run it ONCE on the VPS. Requires:
#   - A Render account (free, no credit card)  https://render.com/register
#   - An API key from                            https://dashboard.render.com/u/settings#api-keys
# ==============================================================

set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

echo ""
echo "${BLUE}═══════════════════════════════════════════════════════${NC}"
echo "${BLUE}  Surveyor Job Dashboard — Render Deployment Setup${NC}"
echo "${BLUE}═══════════════════════════════════════════════════════${NC}"
echo ""

# --- 1. Check prerequisites ---
echo "${YELLOW}[1/5]${NC} Checking prerequisites..."

if ! command -v curl >/dev/null; then
    echo "${RED}ERROR: curl is required.${NC}"
    exit 1
fi

if ! command -v jq >/dev/null; then
    echo "${YELLOW}  Installing jq...${NC}"
    sudo apt-get install -y jq 2>/dev/null || sudo yum install -y jq
fi

# --- 2. Get API key ---
echo ""
echo "${YELLOW}[2/5]${NC} Render API key setup"
echo "  Get an API key from: ${BLUE}https://dashboard.render.com/u/settings#api-keys${NC}"
echo ""
read -s -p "  Paste your Render API key: " RENDER_API_KEY
echo ""

if [ -z "$RENDER_API_KEY" ]; then
    echo "${RED}ERROR: API key is required.${NC}"
    exit 1
fi

# Test the API key
echo -n "  Verifying API key... "
HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" \
    -H "Authorization: Bearer $RENDER_API_KEY" \
    https://api.render.com/v1/owners)
if [ "$HTTP_CODE" != "200" ]; then
    echo "${RED}FAILED (HTTP $HTTP_CODE)${NC}"
    echo "  Check your API key and try again."
    exit 1
fi
echo "${GREEN}OK${NC}"

# Get the owner ID
OWNER_ID=$(curl -s -H "Authorization: Bearer $RENDER_API_KEY" \
    https://api.render.com/v1/owners | jq -r '.[0].owner.id')
echo "  Owner ID: $OWNER_ID"

# --- 3. Get API keys from existing .env ---
echo ""
echo "${YELLOW}[3/5]${NC} Reading API keys from ~/.hermes/.env..."

DEEPSEEK_KEY=$(grep "^DEEPSEEK_API_KEY=" ~/.hermes/.env | cut -d'=' -f2 | tr -d '"' | tr -d "'")
SERPAPI_KEYS=$(grep "^SERPAPI_API_KEYS=" ~/.hermes/.env | cut -d'=' -f2 | tr -d '"' | tr -d "'")

if [ -z "$DEEPSEEK_KEY" ]; then
    echo "${RED}ERROR: DEEPSEEK_API_KEY not found in ~/.hermes/.env${NC}"
    exit 1
fi
if [ -z "$SERPAPI_KEYS" ]; then
    echo "${RED}ERROR: SERPAPI_API_KEYS not found in ~/.hermes/.env${NC}"
    exit 1
fi
echo "  ${GREEN}DEEPSEEK_API_KEY found${NC}"
echo "  ${GREEN}SERPAPI_API_KEYS found${NC}"

# --- 4. Create the Render service ---
echo ""
echo "${YELLOW}[4/5]${NC} Creating Render web service..."

# The service config matches render.yaml
PAYLOAD=$(cat <<EOF
{
  "type": "web_service",
  "name": "surveyor-jobs",
  "ownerId": "$OWNER_ID",
  "repo": "https://github.com/timoranjes/surveyor-jobs",
  "branch": "main",
  "autoDeploy": true,
  "serviceDetails": {
    "runtime": "python",
    "plan": "free",
    "buildCommand": "pip install --upgrade pip && pip install -r backend/requirements.txt",
    "startCommand": "uvicorn backend.main:app --host 0.0.0.0 --port \$PORT",
    "healthCheckPath": "/",
    "envVars": [
      {"key": "PYTHON_VERSION", "value": "3.11.9"},
      {"key": "DB_PATH", "value": "/tmp/jobs.db"},
      {"key": "LLM_LOG_DIR", "value": "/tmp/llm_logs"},
      {"key": "DEEPSEEK_API_KEY", "value": "$DEEPSEEK_KEY"},
      {"key": "SERPAPI_API_KEYS", "value": "$SERPAPI_KEYS"}
    ]
  }
}
EOF
)

CREATE_RESPONSE=$(curl -s -X POST \
    -H "Authorization: Bearer $RENDER_API_KEY" \
    -H "Content-Type: application/json" \
    -d "$PAYLOAD" \
    https://api.render.com/v1/services)

SERVICE_ID=$(echo "$CREATE_RESPONSE" | jq -r '.id' 2>/dev/null)

if [ "$SERVICE_ID" == "null" ] || [ -z "$SERVICE_ID" ]; then
    echo "${RED}Failed to create service. Response:${NC}"
    echo "$CREATE_RESPONSE" | jq . 2>/dev/null || echo "$CREATE_RESPONSE"
    exit 1
fi

SERVICE_URL=$(echo "$CREATE_RESPONSE" | jq -r '.serviceDetails.url' 2>/dev/null)
echo "  ${GREEN}Service created: $SERVICE_ID${NC}"
echo "  Initial URL: $SERVICE_URL"

# --- 5. Trigger first deploy ---
echo ""
echo "${YELLOW}[5/5]${NC} Triggering first deploy..."

DEPLOY_RESPONSE=$(curl -s -X POST \
    -H "Authorization: Bearer $RENDER_API_KEY" \
    -H "Content-Type: application/json" \
    "https://api.render.com/v1/services/$SERVICE_ID/deploys")

DEPLOY_ID=$(echo "$DEPLOY_RESPONSE" | jq -r '.id' 2>/dev/null)
echo "  Deploy ID: $DEPLOY_ID"
echo "  Monitor at: https://dashboard.render.com/web/$SERVICE_ID"

# --- Done ---
echo ""
echo "${GREEN}═══════════════════════════════════════════════════════${NC}"
echo "${GREEN}  Setup complete!${NC}"
echo "${GREEN}═══════════════════════════════════════════════════════${NC}"
echo ""
echo "Next steps:"
echo "  1. Wait ~3-5 min for the first build to complete."
echo "  2. Check deploy status: https://dashboard.render.com/web/$SERVICE_ID"
echo "  3. Once live, the service will be at: $SERVICE_URL"
echo "  4. Then run ${YELLOW}./switch_to_render.sh${NC} to repoint the Cloudflare tunnel."
echo ""
