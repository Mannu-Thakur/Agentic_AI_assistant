@echo off
TITLE AI Assistant - College WiFi Share (Docker)
echo ============================================================
echo   AI Assistant - Campus Wi-Fi Launcher
echo ============================================================
echo.
echo   This script uses Docker Compose for a reliable, multi-user
echo   deployment. All 4 services start automatically:
echo     - PostgreSQL (internal only)
echo     - Redis      (internal only)
echo     - FastAPI Backend (via nginx proxy)
echo     - React Frontend  (nginx on port 80)
echo.
echo   For full setup, run lan_deploy.bat instead.
echo   Launching Docker Compose now...
echo.

docker compose up --build -d
if %errorlevel% neq 0 (
    echo [!] Failed. Is Docker Desktop running?
    pause
    exit /b 1
)

echo.
echo [*] Detecting LAN IP...
for /f "tokens=2 delims=:" %%a in ('ipconfig ^| findstr /i "IPv4"') do (
    set RAW=%%a
    set RAW=!RAW: =!
    if not "!RAW!"=="127.0.0.1" set LAN_IP=!RAW!
)

echo.
echo ============================================================
echo   Chatbot is running!
echo   Share this URL on campus Wi-Fi: http://%LAN_IP%
echo ============================================================
echo.
echo   To stop: docker compose down
echo.
pause
