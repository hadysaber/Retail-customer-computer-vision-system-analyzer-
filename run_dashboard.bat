@echo off
echo Starting Retail Analytics Dashboard...
REM Use the python executable from the .venv to run streamlit
".venv\Scripts\python.exe" -m streamlit run dashboard.py
pause
