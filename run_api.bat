@echo off
echo Starting Python API Server...
echo Ensure you have installed requirements: pip install -r requirements.txt
python -m uvicorn api:app --host 0.0.0.0 --port 8000 --reload
pause
