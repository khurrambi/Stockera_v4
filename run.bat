@echo off
REM Start PharmaStock from Command Prompt, PowerShell or by double-clicking.
REM Creates the .venv and installs requirements on first run; no activation needed.
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
    echo Creating virtual environment in .venv ...
    python -m venv .venv || goto :error
    ".venv\Scripts\python.exe" -m pip install --upgrade pip
    ".venv\Scripts\python.exe" -m pip install -r requirements.txt || goto :error
)

".venv\Scripts\python.exe" -c "import streamlit, pandas, plotly, openpyxl, anthropic, matplotlib, reportlab, docx, pptx" >nul 2>&1
if errorlevel 1 (
    echo Installing requirements ...
    ".venv\Scripts\python.exe" -m pip install -r requirements.txt || goto :error
)

".venv\Scripts\python.exe" -m streamlit run app.py %*
goto :eof

:error
echo.
echo Setup failed. Check that Python 3.10+ is installed and on PATH ^(python --version^).
pause
exit /b 1
