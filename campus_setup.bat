@echo off
setlocal EnableDelayedExpansion
title AI Chatbot - IIIT Campus Launcher
color 0A

:: ?? FIX: Always run from the folder where this .bat file lives ????????????????
cd /d "%~dp0"

echo.
echo ============================================================
echo   AI Chatbot - IIIT Campus Wi-Fi Launcher
echo   Right-click ^> Run as Administrator
echo ============================================================
echo.

:: ?? STEP 1: Firewall ?????????????????????????????????????????
echo [1/4] Opening port 80 in Windows Firewall...
netsh advfirewall firewall delete rule name="AI Chatbot LAN Port 80" >nul 2>&1
netsh advfirewall firewall add rule name="AI Chatbot LAN Port 80" dir=in action=allow protocol=TCP localport=80 >nul 2>&1
if %errorlevel% equ 0 (
    echo       Port 80 - OPEN
) else (
    echo       FAILED - Please right-click and choose "Run as Administrator"
    pause & exit /b 1
)

:: ?? STEP 2: Docker check ?????????????????????????????????????
echo.
echo [2/4] Checking Docker...
docker info >nul 2>&1
if %errorlevel% neq 0 (
    echo       Docker Desktop is not running!
    echo       Open Docker Desktop, wait for the green icon, then run this again.
    pause & exit /b 1
)
echo       Docker is running.

:: ?? STEP 3: Start containers ?????????????????????????????????
echo.
echo [3/4] Starting containers...
echo.
docker compose up -d
echo.
if %errorlevel% neq 0 (
    echo ============================================================
    echo   ERROR: Docker Compose failed. Read the output above.
    echo ============================================================
    pause & exit /b 1
)
echo       Containers started!

:: ?? STEP 4: Wait for healthy ?????????????????????????????????
echo.
echo [4/4] Waiting for chatbot to be ready (up to 60s)...
set /a TRY=0
:wait
timeout /t 4 /nobreak >nul
curl -s -o nul -w "%%{http_code}" http://localhost/api/v1/health 2>nul | findstr "200" >nul
if %errorlevel% equ 0 goto ready
set /a TRY+=1
if %TRY% lss 15 (
    echo       Still starting... [!TRY!/15]
    goto wait
)
echo       Timed out. Run: docker compose logs backend
goto show

:ready
echo       Chatbot is healthy!

:: ?? Detect LAN IP ????????????????????????????????????????????
:show
set LAN_IP=
for /f "tokens=2 delims=:" %%a in ('ipconfig ^| findstr /i "IPv4"') do (
    set RAW=%%a
    set RAW=!RAW: =!
    if not "!RAW!"=="127.0.0.1" if not defined LAN_IP set LAN_IP=!RAW!
)

echo.
echo ============================================================
echo.
echo   Chatbot is LIVE!
echo.
echo   Share this with friends on IIIT Wi-Fi:
echo.
echo        http://%LAN_IP%
echo.
echo   Stop:  docker compose down
echo   Logs:  docker compose logs -f
echo.
echo ============================================================
echo.
pause
