#!/bin/bash
# run_dashboard_test.sh — Check if Flask is running, then run dashboard rendering tests

set -e

# Check if Flask server is already running on port 5050
echo "🔍 Checking if Flask server is running on http://localhost:5050..."
if curl -s http://localhost:5050 > /dev/null 2>&1; then
    echo "✓ Flask server is already running"
else
    echo "⚠️  Flask server not running. Starting it..."
    python tagger_flask.py > /tmp/flask.log 2>&1 &
    FLASK_PID=$!
    echo "   PID: $FLASK_PID"
    echo "   Waiting for server to start..."
    sleep 3

    # Verify it started
    if curl -s http://localhost:5050 > /dev/null 2>&1; then
        echo "✓ Flask server started successfully"
    else
        echo "✗ Failed to start Flask server"
        cat /tmp/flask.log
        exit 1
    fi
fi

# Run the dashboard rendering test
echo ""
echo "📋 Running dashboard rendering tests..."
source test_venv/bin/activate
python test_dashboard_rendering.py
