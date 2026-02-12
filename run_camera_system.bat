@echo off
echo ========================================
echo   Retail Vision Camera System
echo ========================================
echo.
echo Starting camera system...
echo.
echo INSTRUCTIONS:
echo 1. A launcher window will appear
echo 2. Enter camera index (usually 0 for webcam)
echo 3. Click "START MONITORING"
echo 4. Press 'q' to quit, 'h' to toggle heatmap
echo.
echo ========================================
echo.

cd /d "%~dp0"
python editedOnlyOneID.py

pause
