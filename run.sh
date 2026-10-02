#!/usr/bin/env bash
# Start PharmaStock from Git Bash (Windows) or a macOS/Linux shell.
# Creates the .venv and installs requirements on first run; no activation needed.
set -euo pipefail
cd "$(dirname "$0")"

if [ -x ".venv/Scripts/python.exe" ]; then
  PY=".venv/Scripts/python.exe"
elif [ -x ".venv/bin/python" ]; then
  PY=".venv/bin/python"
else
  echo "Creating virtual environment in .venv ..."
  if command -v python >/dev/null 2>&1; then python -m venv .venv; else python3 -m venv .venv; fi
  if [ -x ".venv/Scripts/python.exe" ]; then PY=".venv/Scripts/python.exe"; else PY=".venv/bin/python"; fi
  "$PY" -m pip install --upgrade pip
  "$PY" -m pip install -r requirements.txt
fi

if ! "$PY" -c "import streamlit, pandas, plotly, openpyxl, anthropic, matplotlib, reportlab, docx, pptx" >/dev/null 2>&1; then
  echo "Installing requirements ..."
  "$PY" -m pip install -r requirements.txt
fi

exec "$PY" -m streamlit run app.py "$@"
