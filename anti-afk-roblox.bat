@echo off
REM Anti-AFK for Roblox - double-click to start.
REM
REM Supplies Roblox-specific identity to the generic engine (anti-afk.ps1).
REM "Roblox*" future-proofs against the "RobloxPlayerBeta" name ever changing;
REM "Roblox" title is a fallback. -KeyCode 0x20 = Space, so the character
REM actually jumps in place - this defeats game AFK scripts that watch for
REM real character movement (a no-op key like F13 does not). -WigglePixels 3
REM also nudges the mouse a few px and back for scripts that watch the mouse
REM / camera. Extra args are forwarded, e.g.:
REM   anti-afk-roblox.bat -MaxIntervalMinutes 20 -IdleTriggerSeconds 90

powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0anti-afk\anti-afk.ps1" ^
  -ProcessName "Roblox*" -WindowTitle "Roblox" -KeyCode 0x20 -WigglePixels 3 %*

pause
