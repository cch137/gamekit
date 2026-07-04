#!/bin/bash
# Anti-AFK for Roblox (macOS) - double-click to start.
#
# macOS analog of anti-afk-roblox.bat. Supplies Roblox-specific identity to the
# generic engine (anti-afk/anti-afk.js) and runs it under osascript.
#
# On macOS the running process is "RobloxPlayer"; "Roblox*" future-proofs the
# name and "Roblox" is a fallback. KeyCode=49 = Space, so the character actually
# jumps in place - this defeats game AFK scripts that watch for real character
# movement (a no-op key like F13 does not). WigglePixels=3 also nudges the mouse
# a few px and back for scripts that watch the mouse / camera.
#
# Extra args are forwarded as Key=Value tokens (NOT -Flag value like the .bat),
# because osascript would otherwise treat leading dashes as its own options, e.g.
#   ./anti-afk-roblox.command MaxIntervalMinutes=20 IdleTriggerSeconds=90
#
# FIRST-TIME SETUP:
#   1) Make it double-clickable:  chmod +x anti-afk-roblox.command
#   2) Grant permissions when prompted, or pre-enable your terminal under
#      System Settings > Privacy & Security > Accessibility  and  > Automation.
# Stop: press Ctrl+C in the Terminal window, or just close it.

DIR="$(cd "$(dirname "$0")" && pwd)"

osascript -l JavaScript "$DIR/anti-afk/anti-afk.js" \
  "AppName=RobloxPlayer,Roblox*,Roblox" "WindowTitle=Roblox" "KeyCode=49" "WigglePixels=3" "$@"
