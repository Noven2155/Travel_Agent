@echo off
cd /d "%~dp0"
where py >nul 2>nul
if %errorlevel%==0 (
  py -3.12 -c "import sys" >nul 2>nul
  if not errorlevel 1 (
    py -3.12 scripts\launch_streamlit.py
  ) else (
    py -3 scripts\launch_streamlit.py
  )
) else (
  python scripts\launch_streamlit.py
)
pause
