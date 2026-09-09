@echo off
echo Adding Windows Firewall rule for AI Chatbot (port 80)...
netsh advfirewall firewall add rule name="AI Chatbot LAN Port 80" dir=in action=allow protocol=TCP localport=80 description="AI Assistant Campus LAN - Frontend nginx port"
if %errorlevel% equ 0 (
    echo [+] Firewall rule added successfully!
    echo     Campus devices on the same Wi-Fi can now reach port 80.
) else (
    echo [!] Failed to add rule. Make sure you right-clicked and chose "Run as Administrator".
)
pause
