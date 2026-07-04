#!/bin/bash
# Start the Surveyor Job Dashboard
set -e

cd "$(dirname "$0")"

# Activate venv
if [ ! -d venv ]; then
    python3 -m venv venv
    source venv/bin/activate
    pip install -r backend/requirements.txt
else
    source venv/bin/activate
fi

# Init DB
python3 -c "import sys; sys.path.insert(0,'.'); from backend.database import init_db; init_db()"

# Start server
echo "Starting Surveyor Job Dashboard on http://0.0.0.0:8765"
exec python3 -m uvicorn backend.main:app --host 0.0.0.0 --port 8765 --reload
