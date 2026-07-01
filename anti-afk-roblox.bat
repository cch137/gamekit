@echo off
REM Anti-AFK for Roblox - double-click to start.
REM
REM Supplies Roblox-specific identity to the generic engine (anti-afk.ps1).
REM "Roblox*" future-proofs against the "RobloxPlayerBeta" name ever changing;
REM "Roblox" title is a fallback. Extra args are forwarded, e.g.:
REM   anti-afk-roblox.bat -MaxIntervalMinutes 10 -IdleTriggerMinutes 3

powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0anti-afk\anti-afk.ps1" ^
  -ProcessName "Roblox*" -WindowTitle "Roblox" %*

pause
