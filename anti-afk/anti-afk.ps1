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
# Adaptive timing (all measured since the last poke):
#   - No poke at all until (MaxIntervalMinutes - WindowMinutes) have passed, so
#     pokes are always at least that far apart (10 min with the defaults).
#   - Inside the trailing WindowMinutes window (10..15 min by default) a poke
#     fires as soon as you've been idle long enough - but the required idle time
#     decays linearly from IdleTriggerSeconds down to 0 as the force deadline
#     nears. So early in the window it waits for ~1 min of idle; near the end
#     almost any brief pause triggers it, catching you the moment you step away.
#   - At MaxIntervalMinutes it force-pokes regardless of activity.
#   The re-check interval is itself dynamic: coarse when far from the window,
#   dense inside it, so idle moments are caught promptly without busy-looping.
#
#   If you are actively playing (the target IS the foreground window and you
#   have given input since it was focused), your own input already keeps the
#   game alive, so the poke is skipped - it never interrupts active play. That
#   input is counted as a keepalive, so the next forced poke still lands within
#   MaxIntervalMinutes of it, keeping you under the ~20 min disconnect limit.
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
    # Length of the opportunistic window right before the force point. Pokes may
    # only happen inside it, i.e. from (Max - Window) up to Max minutes since the
    # last poke. Defaults give a 10..15 min window.
    [double]$WindowMinutes = 5,
    # Idle threshold (seconds) required at the START of the window. It decays
    # linearly to 0 by the end, so a poke needs a full minute of idle early on
    # but almost none as the deadline approaches.
    [double]$IdleTriggerSeconds = 60,
    # Dynamic re-check cadence bounds (seconds): coarse (up to Max) far from the
    # window, dense (down to Min) inside it.
    [int]$MinCheckSeconds = 5,
    [int]$MaxCheckSeconds = 60,
    # Virtual-key code to send. 0x7C = F13 (harmless, resets the client's raw
    # idle timer). For games with their own AFK scripts that watch character
    # movement, send a real action instead, e.g. 0x20 = Space (jump in place).
    [int]$KeyCode = 0x7C,
    # How long to hold the key down, in ms. A real press (not an instant tap)
    # is more reliably registered as an in-game action like a jump.
    [int]$KeyHoldMs = 80,
    # Extra safety: nudge the mouse this many pixels and back during each poke,
    # so AFK scripts that watch mouse/camera movement also see activity. The
    # cursor is returned to its exact original position. 0 disables.
    [int]$WigglePixels = 0
)

if ($ProcessName.Count -eq 0 -and [string]::IsNullOrEmpty($WindowTitle)) {
    Write-Host "ERROR: give -ProcessName and/or -WindowTitle so a window can be found." -ForegroundColor Red
    exit 1
}

Add-Type @"
using System;
using System.Diagnostics;
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
    [DllImport("user32.dll")] static extern uint MapVirtualKey(uint uCode, uint uMapType);
    [DllImport("user32.dll")] static extern bool GetLastInputInfo(ref LASTINPUTINFO plii);
    [DllImport("user32.dll")] static extern uint SendInput(uint nInputs, INPUT[] pInputs, int cbSize);
    [DllImport("user32.dll")] static extern bool GetCursorPos(out POINT lpPoint);
    [DllImport("user32.dll")] static extern bool SetCursorPos(int X, int Y);
    [DllImport("kernel32.dll")] static extern uint GetCurrentThreadId();
    [DllImport("kernel32.dll")] static extern uint GetTickCount();

    [StructLayout(LayoutKind.Sequential)]
    struct LASTINPUTINFO { public uint cbSize; public uint dwTime; }
    [StructLayout(LayoutKind.Sequential)]
    struct POINT { public int X; public int Y; }
    [StructLayout(LayoutKind.Sequential)]
    struct MOUSEINPUT { public int dx; public int dy; public uint mouseData; public uint dwFlags; public uint time; public IntPtr dwExtraInfo; }
    [StructLayout(LayoutKind.Sequential)]
    struct INPUT { public uint type; public MOUSEINPUT mi; }

    const int SW_RESTORE = 9;
    const uint KEYEVENTF_KEYUP = 0x0002;
    const uint KEYEVENTF_SCANCODE = 0x0008;
    const uint MOUSEEVENTF_MOVE = 0x0001;

    // Hard ceiling for the whole focus->act->restore cycle. TAIL reserves time
    // for the final ForceForeground(original) so the cycle never exceeds BUDGET.
    const int BUDGET_MS = 500;
    const int TAIL_MS = 50;

    static readonly Random _rng = new Random();
    static int Rand(int lo, int hi) { return _rng.Next(lo, hi + 1); }

    // A jittered key-hold around the base value (never an instant tap).
    static int HoldJitter(int baseMs) {
        int lo = baseMs - 25; if (lo < 30) lo = 30;
        return Rand(lo, baseMs + 35);
    }

    // Sleep for "want" ms, but shortened so the cycle stays within budget.
    static void SleepBudgeted(Stopwatch sw, int want) {
        int remaining = BUDGET_MS - TAIL_MS - (int)sw.ElapsedMilliseconds;
        int s = want < remaining ? want : remaining;
        if (s > 0) Thread.Sleep(s);
    }

    // Send a relative mouse move as genuine input (registers as movement).
    static void MoveRel(int dx, int dy) {
        INPUT[] inp = new INPUT[1];
        inp[0].type = 0;  // INPUT_MOUSE
        inp[0].mi.dx = dx; inp[0].mi.dy = dy;
        inp[0].mi.dwFlags = MOUSEEVENTF_MOVE;
        SendInput(1, inp, Marshal.SizeOf(typeof(INPUT)));
    }

    // Nudge the mouse px pixels and back (with a jittered, budgeted gap), then
    // snap the cursor to its exact original position (correcting edge-clamp drift).
    static void WiggleMouse(int px, Stopwatch sw) {
        if (px <= 0) return;
        POINT p; GetCursorPos(out p);
        MoveRel(px, px);
        SleepBudgeted(sw, Rand(12, 40));
        MoveRel(-px, -px);
        SetCursorPos(p.X, p.Y);
    }

    // Press / release a key including its hardware scan code, so games that read
    // raw/scancode input (not just virtual keys) register it.
    static void KeyDown(byte vk) {
        byte scan = (byte)MapVirtualKey(vk, 0);
        keybd_event(vk, scan, KEYEVENTF_SCANCODE, UIntPtr.Zero);
    }
    static void KeyUp(byte vk) {
        byte scan = (byte)MapVirtualKey(vk, 0);
        keybd_event(vk, scan, KEYEVENTF_SCANCODE | KEYEVENTF_KEYUP, UIntPtr.Zero);
    }

    // Pre-JIT the timing / input helpers so the first real Poke isn't slowed
    // by one-time compilation (which can push it over budget). Side-effect free:
    // no keystroke, no focus change, a 0-pixel mouse no-op restored in place.
    public static void Warmup() {
        Stopwatch sw = Stopwatch.StartNew();
        int j = HoldJitter(80) + Rand(1, 2);
        SleepBudgeted(sw, 1);
        byte scan = (byte)MapVirtualKey(0x20, 0);
        POINT p; GetCursorPos(out p);
        MoveRel(0, 0);
        SetCursorPos(p.X, p.Y);
    }

    // Milliseconds since the last real keyboard/mouse input from the user.
    public static long IdleMillis() {
        LASTINPUTINFO lii = new LASTINPUTINFO();
        lii.cbSize = (uint)Marshal.SizeOf(typeof(LASTINPUTINFO));
        if (!GetLastInputInfo(ref lii)) return 0;
        return (uint)(GetTickCount() - lii.dwTime);
    }

    // True if the given window is currently the foreground (focused) window.
    public static bool IsForeground(IntPtr hWnd) {
        return GetForegroundWindow() == hWnd;
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

    // Briefly focus the target window, send a key (+ optional mouse wiggle),
    // then restore original focus. All delays are jittered and the whole cycle
    // is bounded to BUDGET_MS. Returns the actual cycle duration in ms.
    public static long Poke(IntPtr target, byte keyCode, int holdMs, int wigglePx) {
        if (target == IntPtr.Zero) return 0;
        IntPtr original = GetForegroundWindow();
        bool swap = (target != original);
        Stopwatch sw = Stopwatch.StartNew();

        if (swap) {
            ForceForeground(target);
            SleepBudgeted(sw, Rand(40, 75));   // let the target actually take focus
        }

        KeyDown(keyCode);
        SleepBudgeted(sw, HoldJitter(holdMs)); // hold the key (e.g. a jump)
        KeyUp(keyCode);

        WiggleMouse(wigglePx, sw);

        if (swap) {
            SleepBudgeted(sw, Rand(8, 25));
            if (original != IntPtr.Zero) ForceForeground(original);
        }
        return sw.ElapsedMilliseconds;
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

$windowStart = $MaxIntervalMinutes - $WindowMinutes   # min since last poke before pokes may fire

$who = if ($ProcessName.Count) { $ProcessName -join ", " } else { "title:/$WindowTitle/" }
Write-Host "Anti-AFK started. Target: $who"
Write-Host "Poke window: $windowStart..$MaxIntervalMinutes min since last poke; idle needed decays ${IdleTriggerSeconds}s -> 0 across it; force at $MaxIntervalMinutes min."
Write-Host "Dynamic re-check: $MinCheckSeconds..$MaxCheckSeconds s."
Write-Host "Press Ctrl+C or close this window to stop."

[Afk]::Warmup()                    # pre-JIT so the first poke stays within budget
$lastPoke = [DateTime]::MinValue   # MinValue => poke on the first successful find
$focusedSince = $null              # when the target most recently became foreground

while ($true) {
    $target = Resolve-TargetWindow
    if (-not $target) {
        Write-Host "$(Get-Date -Format 'HH:mm:ss') - waiting: target window not found (not running yet?)"
        $focusedSince = $null
        Start-Sleep -Seconds $MaxCheckSeconds
        continue
    }

    $now = Get-Date
    $idleSec = [Afk]::IdleMillis() / 1000.0
    $lastInput = $now.AddSeconds(-$idleSec)

    # Track how long the target has been the foreground window (conservatively:
    # dated to when we first observed it focused).
    $focused = [Afk]::IsForeground([IntPtr]$target.Handle)
    if ($focused) { if (-not $focusedSince) { $focusedSince = $now } }
    else { $focusedSince = $null }

    # If the user's most recent input happened AFTER the target became focused,
    # that input reached the game and already reset its idle timer. Count it as
    # a keepalive so we don't poke (interrupt) active play - while still keeping
    # lastPoke anchored to a real input, so the force deadline stays < 20 min.
    $userAlive = $focused -and $focusedSince -and ($lastInput -ge $focusedSince)
    $preSince  = if ($lastPoke -eq [DateTime]::MinValue) { [double]::PositiveInfinity } `
                 else { ($now - $lastPoke).TotalMinutes }
    if ($userAlive -and ($lastInput -gt $lastPoke)) { $lastPoke = $lastInput }

    $firstRun  = ($lastPoke -eq [DateTime]::MinValue)
    $sincePoke = if ($firstRun) { [double]::PositiveInfinity } else { ($now - $lastPoke).TotalMinutes }

    # Decide whether to poke, and why.
    $reason = $null
    if ($firstRun) {
        $reason = "first run"
    } elseif ($sincePoke -ge $MaxIntervalMinutes) {
        $reason = "forced ($([math]::Round($sincePoke,1))m)"
    } elseif ($sincePoke -ge $windowStart) {
        # Linear decay of the idle requirement across the window: full at the
        # start, 0 at the force deadline.
        $t = ($sincePoke - $windowStart) / $WindowMinutes            # 0..1
        $requiredIdle = $IdleTriggerSeconds * (1 - $t)
        if ($idleSec -ge $requiredIdle) {
            $reason = "idle $([math]::Round($idleSec))s (needed $([math]::Round($requiredIdle))s)"
        }
    }

    if ($reason) {
        $ms = [Afk]::Poke([IntPtr]$target.Handle, [byte]$KeyCode, [int]$KeyHoldMs, [int]$WigglePixels)
        $lastPoke = Get-Date
        $sincePoke = 0.0
        Write-Host "$(Get-Date -Format 'HH:mm:ss') - poked '$($target.Name)' [$reason] (${ms}ms)"
    } elseif ($userAlive -and ($preSince -ge $windowStart)) {
        # Would have poked, but you're actively playing - skip and let your own
        # input keep it alive.
        Write-Host "$(Get-Date -Format 'HH:mm:ss') - skip: active in $($target.Name) (idle $([math]::Round($idleSec))s)"
    }

    # Dynamic sleep until the next check.
    if ($sincePoke -lt $windowStart) {
        # Far from the window: coarse, but don't overshoot the window opening.
        $secs = ($windowStart - $sincePoke) * 60
        $sleep = [math]::Min($MaxCheckSeconds, [math]::Max($MinCheckSeconds, $secs))
    } else {
        # Inside the window: dense, tightening as the force deadline approaches.
        $secs = ($MaxIntervalMinutes - $sincePoke) * 60
        $sleep = [math]::Min(20, [math]::Max($MinCheckSeconds, $secs / 4))
    }
    Start-Sleep -Seconds ([int][math]::Ceiling($sleep))
}
