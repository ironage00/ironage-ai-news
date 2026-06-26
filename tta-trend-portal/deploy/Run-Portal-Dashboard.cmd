@echo off
setlocal

REM TTA ICT Trend Radar Streamlit dashboard launcher.
REM Run from any directory.

set PORT=8507
set DASHBOARD_DIR=%~dp0..\dashboard

cd /d "%DASHBOARD_DIR%"

echo Starting TTA ICT Trend Radar dashboard on port %PORT%...
python -m streamlit run app.py --server.address 0.0.0.0 --server.port %PORT% --server.headless true
