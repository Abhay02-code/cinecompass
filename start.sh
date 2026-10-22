#!/usr/bin/env sh
set -eu
cd "$(dirname "$0")"
[ -d .venv ] || python3 -m venv .venv
.venv/bin/python -c "import sys; assert (3,10) <= sys.version_info[:2] <= (3,13), 'Use Python 3.10 to 3.13'"
.venv/bin/python -m pip install -r requirements.txt
[ -f .env ] || cp .env.example .env
exec .venv/bin/python app.py
