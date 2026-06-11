@echo off
cd /d "%~dp0"

echo ============================================================
echo   Kuaishou Short Drama Scanner
echo ============================================================
echo.
echo Prerequisites:
echo   1. AScript open on phone (Accessibility Mode)
echo   2. Phone and PC on same WiFi
echo   3. Kuaishou open on Home page
echo.
echo Commands:
echo   0  - Test connection
echo   1  - Search - screenshot - extract author ID
echo   2  - Burst screenshots (multiple shots per video)
echo   3  - Screenshot test (5 shots)
echo   4  - Show UI tree
echo.

set /p TASK_NUM=Enter task number (0-4):

echo.
CALL conda run -n zscq python main.py %TASK_NUM%
echo.

if %ERRORLEVEL%==0 (
    echo Done!
) else (
    echo Error. Check phone connection and Kuaishou status.
)
echo.
pause
