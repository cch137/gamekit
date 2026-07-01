# Anti-AFK - generic idle-keepalive engine (game-agnostic)
#
# Many games (e.g. Roblox) disconnect you after a fixed idle period, and the
# idle timer only resets when *that game's window* receives input. A plain
# background SendInput goes to whatever window is currently focused, so it
# never reaches a backgrounded game - that's why pure-background nudging fails.
#
# On each check this script:
#   1. Locates the target window (by process-name pattern and/or title).
#   2. Decides whether it is time to "poke" it (see the adaptive logic below).
#   3. If so, remembers your current foreground window, very briefly brings
#      the target to the foreground, sends a harmless key, then restores focus
#      to the window you were working in. The swap lasts a few dozen ms.
#
# Adaptive timing:
#   - If you have been idle (no real keyboard/mouse) for >= IdleTriggerMinutes,
#     it pokes opportunistically - while you're away, so nothing is disturbed.
#   - Regardless of activity, it force-pokes once MaxIntervalMinutes has passed
#     since the last poke, so the game never times out even while you work.
#   Because idle periods top up the timer, the (mildly disruptive) forced poke
#   rarely fires unless you are continuously active for the whole window.
#
# This script contains NO game-specific names. Launch it via a wrapper (e.g.
# roblox.bat) that supplies the process/title for the game you want to keep
# alive.
#
# Stop: press Ctrl+C in this window, or just close the window.

param(
    # Process-name patterns to match (wildcards ok, no .exe). Tried in order.
    # e.g. "Roblox*" future-proofs against the "Beta" suffix ever changing.
    [string[]]$ProcessName = @(),
    # Regex matched against the window title. Used to filter process matches
    # and as a fallback that scans every window when no process matches.
    [string]$WindowTitle = "",
    # Hard ceiling: force a poke once this many minutes have passed since the
    # last one, even if you are actively using the computer.
    [double]$MaxIntervalMinutes = 15,
    # If you have been idle at least this long, poke opportunistically.
    [double]$IdleTriggerMinutes = 5,
    # How often to re-evaluate, in seconds.
    [int]$CheckSeconds = 30,
    # Virtual-key code of the harmless key to send. 0x7C = F13 (usually unbound).
    [int]$KeyCode = 0x7C
)

if ($ProcessName.Count -eq 0 -and [string]::IsNullOrEmpty($WindowTitle)) {
    Write-Host "ERROR: give -ProcessName and/or -WindowTitle so a window can be found." -ForegroundColor Red
    exit 1
}

Add-Type @"
using System;
using System.Runtime.InteropServices;
using System.Threading;

public static class Afk {
    [DllImport("user32.dll")] static extern IntPtr GetForegroundWindow();
    [DllImport("user32.dll")] static extern bool SetForegroundWindow(IntPtr hWnd);
    [DllImport("user32.dll")] static extern bool ShowWindow(IntPtr hWnd, int nCmdShow);
    [DllImport("user32.dll")] static extern bool IsIconic(IntPtr hWnd);
    [DllImport("user32.dll")] static extern uint GetWindowThreadProcessId(IntPtr hWnd, out uint pid);
    [DllImport("user32.dll")] static extern bool AttachThreadInput(uint idAttach, uint idAttachTo, bool fAttach);
    [DllImport("user32.dll")] static extern void keybd_event(byte bVk, byte bScan, uint dwFlags, UIntPtr dwExtraInfo);
    [DllImport("user32.dll")] static extern bool GetLastInputInfo(ref LASTINPUTINFO plii);
    [DllImport("kernel32.dll")] static extern uint GetCurrentThreadId();
    [DllImport("kernel32.dll")] static extern uint GetTickCount();

    [StructLayout(LayoutKind.Sequential)]
    struct LASTINPUTINFO { public uint cbSize; public uint dwTime; }

    const int SW_RESTORE = 9;
    const uint KEYEVENTF_KEYUP = 0x0002;

    // Milliseconds since the last real keyboard/mouse input from the user.
    public static long IdleMillis() {
        LASTINPUTINFO lii = new LASTINPUTINFO();
        lii.cbSize = (uint)Marshal.SizeOf(typeof(LASTINPUTINFO));
        if (!GetLastInputInfo(ref lii)) return 0;
        return (uint)(GetTickCount() - lii.dwTime);
    }

    // Force a background window to the foreground, working around Windows'
    // foreground-lock by temporarily attaching input queues.
    static void ForceForeground(IntPtr hWnd) {
        IntPtr fore = GetForegroundWindow();
        uint tmp;
        uint foreThread = GetWindowThreadProcessId(fore, out tmp);
        uint thisThread = GetCurrentThreadId();
        uint targetThread = GetWindowThreadProcessId(hWnd, out tmp);

        AttachThreadInput(thisThread, foreThread, true);
        AttachThreadInput(thisThread, targetThread, true);
        if (IsIconic(hWnd)) ShowWindow(hWnd, SW_RESTORE);
        SetForegroundWindow(hWnd);
        AttachThreadInput(thisThread, targetThread, false);
        AttachThreadInput(thisThread, foreThread, false);
    }

    // Briefly focus the target window, send a key, restore original focus.
    public static void Poke(IntPtr target, byte keyCode) {
        if (target == IntPtr.Zero) return;
        IntPtr original = GetForegroundWindow();

        if (target == original) {
            keybd_event(keyCode, 0, 0, UIntPtr.Zero);
            keybd_event(keyCode, 0, KEYEVENTF_KEYUP, UIntPtr.Zero);
            return;
        }

        ForceForeground(target);
        Thread.Sleep(40);              // let the target actually take focus
        keybd_event(keyCode, 0, 0, UIntPtr.Zero);
        keybd_event(keyCode, 0, KEYEVENTF_KEYUP, UIntPtr.Zero);
        Thread.Sleep(10);

        if (original != IntPtr.Zero) ForceForeground(original);
    }
}
"@

# Resolve the target window handle. Returns a PSObject with Handle/Name/Title,
# or $null if nothing matches right now (the game may not be running yet).
function Resolve-TargetWindow {
    $candidates = @()
    foreach ($pat in $ProcessName) {
        $candidates += Get-Process -Name $pat -ErrorAction SilentlyContinue |
            Where-Object { $_.MainWindowHandle -ne 0 }
    }
    if (-not [string]::IsNullOrEmpty($WindowTitle)) {
        # Filter process matches by title...
        $filtered = $candidates | Where-Object { $_.MainWindowTitle -match $WindowTitle }
        if ($filtered) { $candidates = $filtered }
        elseif ($candidates.Count -eq 0) {
            # ...or, if no process matched at all, scan every window by title.
            $candidates = Get-Process -ErrorAction SilentlyContinue |
                Where-Object { $_.MainWindowHandle -ne 0 -and $_.MainWindowTitle -match $WindowTitle }
        }
    }
    $p = $candidates | Select-Object -First 1
    if (-not $p) { return $null }
    return [PSCustomObject]@{
        Handle = $p.MainWindowHandle
        Name   = $p.ProcessName
        Title  = $p.MainWindowTitle
    }
}

$who = if ($ProcessName.Count) { $ProcessName -join ", " } else { "title:/$WindowTitle/" }
Write-Host "Anti-AFK started. Target: $who"
Write-Host "Force every $MaxIntervalMinutes min; opportunistic when idle >= $IdleTriggerMinutes min; checking every $CheckSeconds s."
Write-Host "Press Ctrl+C or close this window to stop."

$lastPoke = [DateTime]::MinValue   # MinValue => poke on the first successful find

while ($true) {
    $target = Resolve-TargetWindow
    if (-not $target) {
        Write-Host "$(Get-Date -Format 'HH:mm:ss') - waiting: target window not found (not running yet?)"
        Start-Sleep -Seconds $CheckSeconds
        continue
    }

    $idleMin = [Afk]::IdleMillis() / 60000.0
    $sincePoke = ((Get-Date) - $lastPoke).TotalMinutes

    $forced = $sincePoke -ge $MaxIntervalMinutes
    $opportunistic = ($idleMin -ge $IdleTriggerMinutes) -and ($sincePoke -ge $IdleTriggerMinutes)

    if ($forced -or $opportunistic) {
        [Afk]::Poke([IntPtr]$target.Handle, [byte]$KeyCode)
        $lastPoke = Get-Date
        $reason = if ($forced) { "forced ($([math]::Round($sincePoke,1))m since last)" }
                  else { "idle $([math]::Round($idleMin,1))m" }
        Write-Host "$(Get-Date -Format 'HH:mm:ss') - poked '$($target.Name)' [$reason]"
    }

    Start-Sleep -Seconds $CheckSeconds
}
