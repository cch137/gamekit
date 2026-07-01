# gamekit

A small collection of lightweight, dependency-free game utilities for Windows.
Double-click the `.bat` launcher in this folder to start a tool.

## Tools

| Tool | Launch | What it does |
|------|--------|--------------|
| **Anti-AFK** | `anti-afk.bat` | Sends a tiny mouse nudge every N minutes (default 15) to keep a game from disconnecting you for being idle. Stop by closing its window. |
| **Auto Clicker** | `auto-clicker.bat` | Draggable, semi-transparent overlay that auto-clicks at a set CPS. Toggle with the on-screen button or a configurable hotkey (default F6). |

## Layout

```
.
├── anti-afk.bat          # launcher (root)
├── auto-clicker.bat      # launcher (root)
├── anti-afk/
│   └── anti-afk.ps1
└── auto-clicker/
    └── auto-clicker.py
```

Each tool lives in its own folder; launchers stay in the root for easy access.
To add a new tool: create a `tool-name/` folder for its code and a
`tool-name.bat` launcher in the root.

## Requirements

- Windows
- Python 3 (for the Auto Clicker). Anti-AFK uses PowerShell only.

## Note

These automate input at the OS level. Using them with online games may violate
the game's terms of service — use at your own risk.
