@echo off
setlocal EnableDelayedExpansion
TITLE AI Assistant - Campus LAN Deployment

echo.
echo ============================================================
echo   AI Assistant - Campus Wi-Fi LAN Deployment
echo   Using Docker Compose (Production Mode)
echo ============================================================
echo.

:: ?? 1. Detect LAN IP ?????????????????????????????????????????????????????????
echo [*] Detecting LAN IP address...
set LAN_IP=
for /f "tokens=2 delims=:" %%a in ('ipconfig ^| findstr /i "IPv4" ^| findstr "172\. 192\.168\. 10\."') do (
    set RAW=%%a
    set RAW=!RAW: =!
    if not defined LAN_IP set LAN_IP=!RAW!
)

if not defined LAN_IP (
    for /f "tokens=2 delims=:" %%a in ('ipconfig ^| findstr /i "IPv4"') do (
        set RAW=%%a
        set RAW=!RAW: =!
        if not "!RAW!"=="127.0.0.1" if not defined LAN_IP set LAN_IP=!RAW!
    )
)

if not defined LAN_IP (
    echo [!] Could not detect LAN IP. Are you connected to campus Wi-Fi?
    pause
    exit /b 1
)

echo [+] LAN IP detected: %LAN_IP%
echo.

:: ?? 2. Check Docker is running ????????????????????????????????????????????????
echo [*] Checking Docker...
docker info >nul 2>&1
if %errorlevel% neq 0 (
    echo [!] Docker is not running! Start Docker Desktop first.
    pause
    exit /b 1
)
echo [+] Docker is running

:: ?? 3. Build and start all containers ?????????????????????????????????????????
echo.
echo [*] Building and starting all containers...
docker compose up --build -d

if %errorlevel% neq 0 (
    echo [!] Docker Compose failed. Check errors above.
    echo     Run: docker compose logs backend
    pause
    exit /b 1
)

:: ?? 4. Wait for health ????????????????????????????????????????????????????????
echo.
echo [*] Waiting for backend health check (up to 60s)...
set /a RETRIES=0
:healthloop
timeout /t 5 /nobreak >nul
curl -s -o nul -w "%%{http_code}" http://localhost/api/v1/health 2>nul | findstr "200" >nul
if %errorlevel% equ 0 goto healthy
set /a RETRIES+=1
if %RETRIES% lss 12 (
    echo     ... still starting [%RETRIES%/12]
    goto healthloop
)
echo [!] Health check timed out. Run: docker compose logs backend

:healthy
echo [+] All services are up!

:: ?? 5. Show access URLs ???????????????????????????????????????????????????????
echo.
echo ============================================================
echo   DEPLOYMENT COMPLETE
echo ============================================================
echo.
echo   YOUR LAPTOP:       http://localhost
echo   CAMPUS DEVICES:    http://%LAN_IP%
echo.
echo   Share with classmates on the same Wi-Fi:
echo.
echo        >>> http://%LAN_IP% <<<
echo.
echo ============================================================
echo.
echo   View logs:    docker compose logs -f
echo   Stop:         docker compose down
echo   Restart:      docker compose up -d
echo.
echo   FIREWALL NOTE: If classmates cannot connect, open a new
echo   PowerShell as Administrator and run:
echo.
echo   netsh advfirewall firewall add rule name="AI Chatbot Port 80" dir=in action=allow protocol=TCP localport=80
echo.
echo ============================================================
pause
