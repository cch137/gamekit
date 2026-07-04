// Anti-AFK - generic idle-keepalive engine (game-agnostic), macOS edition.
//
// This is the macOS port of anti-afk.ps1. Same idea, same adaptive timing, same
// CLI-driven "supply the game's identity from a wrapper" design - just built on
// macOS primitives instead of Win32:
//   - idle time        -> ioreg HIDIdleTime   (was GetLastInputInfo)
//   - focus a window   -> System Events        (was SetForegroundWindow)
//   - send a key        -> System Events keyCode (was keybd_event)
//   - mouse wiggle      -> Quartz/CoreGraphics   (was SendInput mouse move)
// Everything here uses only tools that ship with macOS. Run it via osascript:
//   osascript -l JavaScript anti-afk.js AppName=RobloxPlayer,Roblox* KeyCode=49
// Normally you launch it through a wrapper (e.g. anti-afk-roblox.command) that
// supplies the identity for the game you want to keep alive.
//
// Why the focus swap? Many games (e.g. Roblox) disconnect you after a fixed idle
// period, and that timer only resets when *that game's window* receives input. A
// key sent while another app is focused never reaches a backgrounded game. So on
// each poke this script remembers your current frontmost app, briefly brings the
// target to the front, sends a harmless key (+ optional mouse wiggle), then
// restores focus to the app you were using. The swap lasts a few dozen ms.
//
// Adaptive timing (all measured since the last poke) - identical to the Windows
// engine:
//   - No poke until (MaxIntervalMinutes - WindowMinutes) have passed, so pokes
//     are always at least that far apart (10 min with the defaults).
//   - Inside the trailing WindowMinutes window a poke fires as soon as you've
//     been idle long enough, but the required idle time decays linearly from
//     IdleTriggerSeconds down to 0 as the force deadline nears.
//   - At MaxIntervalMinutes it force-pokes regardless of activity.
//   The re-check interval is itself dynamic: coarse far from the window, dense
//   inside it.
//   If you are actively playing (target IS frontmost and you have given input
//   since it was focused) your own input already keeps the game alive, so the
//   poke is skipped - it never interrupts active play. That input is counted as
//   a keepalive so the next forced poke still lands within MaxIntervalMinutes.
//
// PERMISSIONS: controlling other apps and sending keystrokes requires macOS to
// trust the app that runs this script. The FIRST run will prompt, and/or you
// must enable your terminal (Terminal.app / iTerm) under:
//   System Settings > Privacy & Security > Accessibility     (send keys / mouse)
//   System Settings > Privacy & Security > Automation        (control System Events)
// Optional mouse wiggle additionally needs Accessibility; if it can't run it is
// silently skipped and the key poke still works.
//
// Stop: press Ctrl+C in the Terminal window, or just close it.

ObjC.import('Foundation');

// ---- tiny stdout logger (line-buffered, shows up in Terminal) --------------
function log(s) {
    var line = $.NSString.stringWithString(String(s) + "\n");
    $.NSFileHandle.fileHandleWithStandardOutput.writeData(
        line.dataUsingEncoding($.NSUTF8StringEncoding));
}
function hms() { return new Date().toTimeString().slice(0, 8); }
function sleepMs(ms) { $.NSThread.sleepForTimeInterval(ms / 1000.0); }
function rand(lo, hi) { return Math.floor(Math.random() * (hi - lo + 1)) + lo; }

// ---- CLI parsing: Key=Value tokens (no leading dashes, so osascript doesn't
// try to treat them as its own options; wildcards must be quoted in the shell)
function parseArgs(argv, defaults) {
    var o = {};
    for (var k in defaults) o[k] = defaults[k];
    for (var i = 0; i < argv.length; i++) {
        var tok = String(argv[i]);
        var eq = tok.indexOf('=');
        if (eq < 0) continue;
        var key = tok.slice(0, eq).toLowerCase();
        var val = tok.slice(eq + 1);
        switch (key) {
            case 'appname':
            case 'processname':
                o.AppName = val.split(',').map(function (s) { return s.trim(); })
                    .filter(function (s) { return s.length; });
                break;
            case 'windowtitle':          o.WindowTitle = val; break;
            case 'maxintervalminutes':   o.MaxIntervalMinutes = parseFloat(val); break;
            case 'windowminutes':        o.WindowMinutes = parseFloat(val); break;
            case 'idletriggerseconds':   o.IdleTriggerSeconds = parseFloat(val); break;
            case 'mincheckseconds':      o.MinCheckSeconds = parseInt(val, 10); break;
            case 'maxcheckseconds':      o.MaxCheckSeconds = parseInt(val, 10); break;
            case 'keycode':              o.KeyCode = parseInt(val, 10); break;
            case 'wigglepixels':         o.WigglePixels = parseInt(val, 10); break;
        }
    }
    return o;
}

// ---- optional mouse wiggle via Quartz. Built lazily; if the ObjC bridge or
// permissions don't cooperate it returns null and wiggling is skipped, leaving
// the key poke fully functional. Constants inlined to avoid missing-symbol
// issues: kCGHIDEventTap=0, kCGEventMouseMoved=5, kCGMouseButtonLeft=0.
function buildWiggle() {
    try {
        ObjC.import('CoreGraphics');
        return function (px) {
            var cur = $.CGEventCreate(null);
            var p = $.CGEventGetLocation(cur);
            var x = p.x, y = p.y;
            var e1 = $.CGEventCreateMouseEvent(null, 5, { x: x + px, y: y + px }, 0);
            $.CGEventPost(0, e1);
            $.NSThread.sleepForTimeInterval(rand(12, 40) / 1000.0);
            var e2 = $.CGEventCreateMouseEvent(null, 5, { x: x, y: y }, 0);
            $.CGEventPost(0, e2);   // return the cursor to its exact origin
        };
    } catch (e) { return null; }
}

function run(argv) {
    var app = Application.currentApplication();
    app.includeStandardAdditions = true;     // enables doShellScript
    var SE = Application('System Events');

    var opts = parseArgs(argv, {
        AppName: [],
        WindowTitle: "",
        MaxIntervalMinutes: 15,
        WindowMinutes: 5,
        IdleTriggerSeconds: 60,
        MinCheckSeconds: 5,
        MaxCheckSeconds: 60,
        KeyCode: 105,          // F13 (harmless). Roblox wrapper overrides -> 49 (Space).
        WigglePixels: 0
    });

    if (opts.AppName.length === 0 && !opts.WindowTitle) {
        log("ERROR: give AppName= and/or WindowTitle= so a target can be found.");
        return;
    }

    // Compile the window-title regex once (not per loop). A malformed pattern
    // must not crash the loop, so on failure warn and disable title matching.
    var titleRe = null;
    if (opts.WindowTitle) {
        try { titleRe = new RegExp(opts.WindowTitle, 'i'); }
        catch (e) { log("WARN: invalid WindowTitle regex /" + opts.WindowTitle + "/ - ignoring it."); }
    }

    // ---- idle seconds since the last real HID (keyboard/mouse) input --------
    function idleSeconds() {
        try {
            var out = app.doShellScript(
                "ioreg -c IOHIDSystem | awk '/HIDIdleTime/{print $NF; exit}'");
            var ns = parseFloat(out);
            return isFinite(ns) ? ns / 1e9 : 0;
        } catch (e) { return 0; }
    }

    // ---- name of the frontmost app process, or null ------------------------
    function frontmostName() {
        try { return SE.applicationProcesses.whose({ frontmost: true })[0].name(); }
        catch (e) { return null; }
    }

    // ---- bring a process to the front by exact name ------------------------
    function setFrontmost(name) {
        try { SE.applicationProcesses.byName(name).frontmost = true; return true; }
        catch (e) {
            try { Application(name).activate(); return true; } catch (e2) { return false; }
        }
    }

    // ---- turn a wildcard pattern ("Roblox*") into a case-insensitive regex --
    function wildcardToRegex(pat) {
        var esc = pat.replace(/[.+^${}()|[\]\\]/g, '\\$&').replace(/\*/g, '.*').replace(/\?/g, '.');
        return new RegExp('^' + esc + '$', 'i');
    }

    // ---- resolve the target process name, or null if not running yet -------
    function resolveTarget() {
        var names;
        try { names = SE.applicationProcesses.name(); } catch (e) { return null; }
        // Match by AppName patterns first.
        if (opts.AppName.length) {
            var pats = opts.AppName.map(wildcardToRegex);
            for (var i = 0; i < names.length; i++) {
                for (var j = 0; j < pats.length; j++) {
                    if (pats[j].test(names[i])) return names[i];
                }
            }
        }
        // Fallback: scan window titles by regex (best effort; needs Accessibility).
        if (titleRe) {
            for (var k = 0; k < names.length; k++) {
                if (titleRe.test(names[k])) return names[k];
                try {
                    var wins = SE.applicationProcesses.byName(names[k]).windows.name();
                    for (var w = 0; w < wins.length; w++) {
                        if (titleRe.test(wins[w])) return names[k];
                    }
                } catch (e) { /* app doesn't expose windows to AX; ignore */ }
            }
        }
        return null;
    }

    // ---- one focus->key(->wiggle)->restore cycle; returns duration in ms ----
    var wiggleFn = null, wiggleTried = false;
    function poke(targetName) {
        var original = frontmostName();
        var swap = (original !== targetName);
        var t0 = Date.now();

        if (swap) {
            setFrontmost(targetName);
            sleepMs(rand(50, 90));            // let the target actually take focus
        }

        try { SE.keyCode(opts.KeyCode); } catch (e) { /* Accessibility not granted yet */ }

        if (opts.WigglePixels > 0) {
            if (!wiggleTried) { wiggleTried = true; wiggleFn = buildWiggle(); }
            if (wiggleFn) {
                try { wiggleFn(opts.WigglePixels); }
                catch (e) { wiggleFn = null; log(hms() + " - mouse wiggle disabled: " + e); }
            }
        }

        if (swap && original) {
            sleepMs(rand(8, 25));
            setFrontmost(original);          // restore the app you were using
        }
        return Date.now() - t0;
    }

    var windowStart = opts.MaxIntervalMinutes - opts.WindowMinutes;   // min before pokes may fire
    var who = opts.AppName.length ? opts.AppName.join(", ") : ("title:/" + opts.WindowTitle + "/");

    log("Anti-AFK started (macOS). Target: " + who);
    log("Poke window: " + windowStart + ".." + opts.MaxIntervalMinutes +
        " min since last poke; idle needed decays " + opts.IdleTriggerSeconds +
        "s -> 0 across it; force at " + opts.MaxIntervalMinutes + " min.");
    log("Dynamic re-check: " + opts.MinCheckSeconds + ".." + opts.MaxCheckSeconds + " s.");
    log("Press Ctrl+C or close this window to stop.");

    var MIN_DATE = -8640000000000000;   // sentinel "never poked"
    var lastPoke = MIN_DATE;            // => poke on the first successful find
    var focusedSince = null;            // when the target most recently became frontmost

    while (true) {
        var target = resolveTarget();
        if (!target) {
            log(hms() + " - waiting: target not found (not running yet?)");
            focusedSince = null;
            sleepMs(opts.MaxCheckSeconds * 1000);
            continue;
        }

        var now = Date.now();
        var idleSec = idleSeconds();
        var lastInput = now - idleSec * 1000;

        // Track how long the target has been frontmost (dated to first sighting).
        var focused = (frontmostName() === target);
        if (focused) { if (!focusedSince) focusedSince = now; }
        else { focusedSince = null; }

        // If your most recent input landed AFTER the target became frontmost, it
        // reached the game and already reset its idle timer. Count it as a
        // keepalive so we don't poke (interrupt) active play - while still
        // anchoring lastPoke to a real input, keeping the force deadline honest.
        var userAlive = focused && focusedSince && (lastInput >= focusedSince);
        var preSince = (lastPoke === MIN_DATE) ? Infinity : (now - lastPoke) / 60000.0;
        if (userAlive && (lastInput > lastPoke)) lastPoke = lastInput;

        var firstRun = (lastPoke === MIN_DATE);
        var sincePoke = firstRun ? Infinity : (now - lastPoke) / 60000.0;

        // Decide whether to poke, and why.
        var reason = null;
        if (firstRun) {
            reason = "first run";
        } else if (sincePoke >= opts.MaxIntervalMinutes) {
            reason = "forced (" + sincePoke.toFixed(1) + "m)";
        } else if (sincePoke >= windowStart) {
            var t = (sincePoke - windowStart) / opts.WindowMinutes;      // 0..1
            var requiredIdle = opts.IdleTriggerSeconds * (1 - t);
            if (idleSec >= requiredIdle) {
                reason = "idle " + Math.round(idleSec) + "s (needed " +
                    Math.round(requiredIdle) + "s)";
            }
        }

        if (reason) {
            var ms = poke(target);
            lastPoke = Date.now();
            sincePoke = 0.0;
            log(hms() + " - poked '" + target + "' [" + reason + "] (" + ms + "ms)");
        } else if (userAlive && (preSince >= windowStart)) {
            // Would have poked, but you're actively playing - let your own input
            // keep it alive.
            log(hms() + " - skip: active in " + target + " (idle " + Math.round(idleSec) + "s)");
        }

        // Dynamic sleep until the next check.
        var sleep;
        if (sincePoke < windowStart) {
            // Far from the window: coarse, but don't overshoot the window opening.
            var secs = (windowStart - sincePoke) * 60;
            sleep = Math.min(opts.MaxCheckSeconds, Math.max(opts.MinCheckSeconds, secs));
        } else {
            // Inside the window: dense, tightening toward the force deadline.
            var secs2 = (opts.MaxIntervalMinutes - sincePoke) * 60;
            sleep = Math.min(20, Math.max(opts.MinCheckSeconds, secs2 / 4));
        }
        sleepMs(Math.ceil(sleep) * 1000);
    }
}
