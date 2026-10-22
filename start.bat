@echo off
setlocal
cd /d "%~dp0"
if exist ".venv\Scripts\python.exe" goto install
where py >nul 2>nul
if errorlevel 1 goto usepython
py -3 -m venv .venv
if errorlevel 1 goto fail
goto install
:usepython
where python >nul 2>nul
if errorlevel 1 goto missing
python -m venv .venv
if errorlevel 1 goto fail
:install
.venv\Scripts\python.exe -c "import sys; assert (3,10) <= sys.version_info[:2] <= (3,13), 'Use Python 3.10 to 3.13; Python 3.11 recommended.'"
if errorlevel 1 goto fail
.venv\Scripts\python.exe -m pip install -r requirements.txt
if errorlevel 1 goto fail
if not exist .env copy .env.example .env >nul
echo.
echo Open http://127.0.0.1:5000 in your browser.
echo Add your TMDB_READ_TOKEN to .env for live movies.
echo Press Ctrl+C to stop.
.venv\Scripts\python.exe app.py
pause
exit /b
:missing
echo Python not found. Install Python 3.11 from python.org, enable Add to PATH, and retry.
pause
exit /b 1
:fail
echo Setup failed. Read the error above and the README troubleshooting section.
pause
exit /b 1
