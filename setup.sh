#!/usr/bin/env bash
# Setup script for Nvoids Job Application Bot
set -e

echo "========================================================="
echo "   Setting up Nvoids Job Application Bot"
echo "========================================================="

# 1. Ensure required directories exist
mkdir -p resumes config templates data

# 2. Check if .env exists, if not create from example
if [ ! -f .env ]; then
    if [ -f .env.example ]; then
        cp .env.example .env
        echo "Created .env from .env.example. Please update your SMTP credentials in .env."
    fi
fi

# 3. Create virtual environment if requested/preferred
if [ ! -d "venv" ]; then
    echo "Creating Python virtual environment in ./venv..."
    python3 -m venv venv
    source venv/bin/activate
    pip install --upgrade pip || true
    pip install -r requirements.txt || true
else
    source venv/bin/activate
fi

echo ""
echo "Setup complete!"
echo "To test matching:           python3 main.py match-check"
echo "To preview recent jobs:     python3 main.py scrape-only"
echo "To run safe dry-run scan:   python3 main.py run --dry-run"
echo "To run live bot:            python3 main.py run --live"
echo "========================================================="
