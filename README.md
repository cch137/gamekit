# gamekit

A small collection of lightweight, dependency-free game utilities for Windows.
Double-click the `.bat` launcher in this folder to start a tool.

## Tools

| Tool | Launch | What it does |
|------|--------|--------------|
| **Anti-AFK (Roblox)** | `anti-afk-roblox.bat` | Keeps Roblox from disconnecting you for being idle. Briefly focuses the Roblox window, sends a harmless key, then restores focus to what you were doing. Pokes opportunistically while you're idle, and force-pokes at most every 15 min. Stop by closing its window. |
| **Auto Clicker** | `auto-clicker.bat` | Draggable, semi-transparent overlay that auto-clicks at a set CPS. Toggle with the on-screen button or a configurable hotkey (default F6). |

## Requirements

- Windows
- Python 3 (for the Auto Clicker). Anti-AFK uses PowerShell only.

## Note

These automate input at the OS level. Using them with online games may violate
the game's terms of service — use at your own risk.
