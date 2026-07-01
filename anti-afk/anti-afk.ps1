# Anti-AFK for Roblox
#
# Sends a tiny mouse "nudge" (move right 1px then left 1px, so the cursor
# does not actually move) via the Windows SendInput API every interval,
# which registers as real user input and resets the idle timer.
#
# Note: this input goes to the focused window / system level; it cannot be
# targeted only at a backgrounded Roblox. Whether running it in the
# background alone is enough to stop Roblox's 20-minute disconnect is NOT
# yet verified - test it yourself for 25-30 minutes.
#
# Stop: press Ctrl+C in this window, or just close the window.

param(
    [double]$IntervalMinutes = 15
)

Add-Type @"
using System;
using System.Runtime.InteropServices;
public static class Afk {
    [StructLayout(LayoutKind.Sequential)]
    struct MOUSEINPUT { public int dx; public int dy; public uint mouseData; public uint dwFlags; public uint time; public IntPtr dwExtraInfo; }
    [StructLayout(LayoutKind.Sequential)]
    struct INPUT { public uint type; public MOUSEINPUT mi; }
    [DllImport("user32.dll", SetLastError=true)]
    static extern uint SendInput(uint nInputs, INPUT[] pInputs, int cbSize);
    const uint MOUSEEVENTF_MOVE = 0x0001;
    public static void Nudge() {
        INPUT[] inp = new INPUT[2];
        inp[0].mi.dx = 1;  inp[0].mi.dwFlags = MOUSEEVENTF_MOVE;
        inp[1].mi.dx = -1; inp[1].mi.dwFlags = MOUSEEVENTF_MOVE;
        SendInput(2, inp, Marshal.SizeOf(typeof(INPUT)));
    }
}
"@

Write-Host "Anti-AFK started. Sending input every $IntervalMinutes min. Press Ctrl+C or close this window to stop."

while ($true) {
    [Afk]::Nudge()
    Write-Host "$(Get-Date -Format 'HH:mm:ss') - input sent"
    Start-Sleep -Seconds ([int]($IntervalMinutes * 60))
}
