import ctypes
import datetime as dt
import sys
import threading
import time
import tkinter as tk
from ctypes import wintypes
import winsound

user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32

MUTEX_NAME = "Global\\FloatingAlarm_SingleInstance"
ERROR_ALREADY_EXISTS = 183
MONITOR_DEFAULTTONEAREST = 2


class MONITORINFO(ctypes.Structure):
    _fields_ = [
        ("cbSize", wintypes.DWORD),
        ("rcMonitor", wintypes.RECT),
        ("rcWork", wintypes.RECT),
        ("dwFlags", wintypes.DWORD),
    ]


def acquire_single_instance_lock():
    kernel32.CreateMutexW.restype = wintypes.HANDLE
    handle = kernel32.CreateMutexW(None, False, MUTEX_NAME)

    if kernel32.GetLastError() == ERROR_ALREADY_EXISTS:
        user32.MessageBoxW(None, "Floating Alarm is already running.",
                           "Floating Alarm", 0x40)
        sys.exit(0)

    return handle


def get_workarea(hwnd=None):
    if hwnd:
        monitor = user32.MonitorFromWindow(wintypes.HWND(hwnd), MONITOR_DEFAULTTONEAREST)
        info = MONITORINFO()
        info.cbSize = ctypes.sizeof(MONITORINFO)

        if user32.GetMonitorInfoW(monitor, ctypes.byref(info)):
            r = info.rcWork
            return r.left, r.top, r.right, r.bottom

    return 0, 0, user32.GetSystemMetrics(0), user32.GetSystemMetrics(1)


class FloatingAlarm:
    BG = "#0f172a"
    CARD = "#111827"
    CARD_2 = "#1f2937"
    BORDER = "#334155"
    TEXT = "#e5e7eb"
    MUTED = "#94a3b8"
    ACCENT = "#38bdf8"
    ACCENT_DARK = "#0284c7"
    DANGER = "#ef4444"
    GREEN = "#22c55e"

    FONT = "Segoe UI"

    def __init__(self):
        self.target_time = None
        self.drag_dx = 0
        self.drag_dy = 0
        self.mode = "float"

        self.root = tk.Tk()
        self.root.title("Floating Alarm")
        self.root.configure(bg=self.BG)
        self.root.protocol("WM_DELETE_WINDOW", self.close)

        self.status_var = tk.StringVar(value="No alarm")
        self.detail_var = tk.StringVar(value="Double-click the bubble to open")

        self._build_float_ui()
        self._build_panel_ui()

        self.show_float(initial=True)
        self._tick()

    def _btn(self, parent, text, command, bg=None, fg="white", width:float | str=320):
        return tk.Button(
            parent,
            text=text,
            command=command,
            width=width,
            bg=bg or self.ACCENT_DARK,
            fg=fg,
            activebackground=bg or self.ACCENT,
            activeforeground="white",
            relief="flat",
            bd=0,
            padx=12,
            pady=7,
            cursor="hand2",
            font=(self.FONT, 9, "bold"),
        )

    def _entry(self, parent, text=""):
        e = tk.Entry(
            parent,
            bg="#020617",
            fg=self.TEXT,
            insertbackground=self.TEXT,
            relief="flat",
            highlightthickness=1,
            highlightbackground=self.BORDER,
            highlightcolor=self.ACCENT,
            font=(self.FONT, 10),
            justify="center",
        )
        e.insert(0, text)
        return e

    def _build_float_ui(self):
        self.float_outer = tk.Frame(self.root, bg=self.ACCENT)

        self.float_card = tk.Frame(self.float_outer, bg=self.CARD, padx=10, pady=8)
        self.float_card.pack(padx=1, pady=1)

        self.float_icon = tk.Label(
            self.float_card,
            text="⏰",
            bg=self.CARD,
            fg=self.ACCENT,
            font=(self.FONT, 22, "bold"),
        )
        self.float_icon.pack()

        self.float_status = tk.Label(
            self.float_card,
            textvariable=self.status_var,
            bg=self.CARD,
            fg=self.TEXT,
            font=(self.FONT, 8, "bold"),
        )
        self.float_status.pack()

        self.float_hint = tk.Label(
            self.float_card,
            text="double-click",
            bg=self.CARD,
            fg=self.MUTED,
            font=(self.FONT, 7),
        )
        self.float_hint.pack()

        for w in (self.float_outer, self.float_card, self.float_icon,
                  self.float_status, self.float_hint):
            w.bind("<Button-1>", self._start_drag)
            w.bind("<B1-Motion>", self._on_drag)
            w.bind("<ButtonRelease-1>", self._end_drag)
            w.bind("<Double-Button-1>", lambda e: self.show_panel())
            w.bind("<Button-3>", lambda e: self.close())

    def _build_panel_ui(self):
        self.panel = tk.Frame(self.root, bg=self.BG, padx=18, pady=16)

        header = tk.Frame(self.panel, bg=self.BG)
        header.pack(fill="x")

        tk.Label(
            header,
            text="Floating Alarm",
            bg=self.BG,
            fg=self.TEXT,
            font=(self.FONT, 16, "bold"),
        ).pack(side="left")

        self._btn(header, "Float", self.show_float, bg=self.CARD_2).pack(side="right")

        body = tk.Frame(self.panel, bg=self.BG)
        body.pack(fill="both", expand=True, pady=(18, 0))

        row1 = tk.Frame(body, bg=self.BG)
        row1.pack(fill="x", pady=6)

        tk.Label(
            row1,
            text="Ring after",
            bg=self.BG,
            fg=self.MUTED,
            font=(self.FONT, 10),
            width=12,
            anchor="w",
        ).pack(side="left")

        self.minutes_entry = self._entry(row1, "10")
        self.minutes_entry.pack(side="left", fill="x", expand=True, padx=(0, 8))

        tk.Label(row1, text="min", bg=self.BG, fg=self.MUTED).pack(side="left", padx=(0, 8))
        self._btn(row1, "Set", self.set_after_minutes, width=7).pack(side="left")

        row2 = tk.Frame(body, bg=self.BG)
        row2.pack(fill="x", pady=6)

        tk.Label(
            row2,
            text="Ring at",
            bg=self.BG,
            fg=self.MUTED,
            font=(self.FONT, 10),
            width=12,
            anchor="w",
        ).pack(side="left")

        self.time_entry = self._entry(row2, "08:30")
        self.time_entry.pack(side="left", fill="x", expand=True, padx=(0, 8))

        self._btn(row2, "Set", self.set_at_time, width=7).pack(side="left")

        status_box = tk.Frame(body, bg=self.CARD, padx=12, pady=10)
        status_box.pack(fill="x", pady=(16, 8))

        tk.Label(
            status_box,
            textvariable=self.status_var,
            bg=self.CARD,
            fg=self.TEXT,
            font=(self.FONT, 12, "bold"),
        ).pack(anchor="w")

        tk.Label(
            status_box,
            textvariable=self.detail_var,
            bg=self.CARD,
            fg=self.MUTED,
            font=(self.FONT, 9),
        ).pack(anchor="w", pady=(4, 0))

        footer = tk.Frame(body, bg=self.BG)
        footer.pack(fill="x", pady=(10, 0))

        self._btn(footer, "Cancel Alarm", self.cancel_alarm, bg=self.DANGER).pack(side="left")
        self._btn(footer, "Close", self.close, bg=self.CARD_2).pack(side="right")

    def _apply_window_flags(self, floating):
        self.root.withdraw()
        self.root.overrideredirect(floating)
        self.root.attributes("-topmost", floating)
        self.root.attributes("-alpha", 0.96 if floating else 1.0)
        self.root.deiconify()

    def show_float(self, initial=False):
        self.mode = "float"

        x = self.root.winfo_x()
        y = self.root.winfo_y()

        self.panel.pack_forget()
        self.float_outer.pack(fill="both", expand=True)

        self.root.minsize(1, 1)
        self._apply_window_flags(True)
        self.root.update_idletasks()

        w = self.float_outer.winfo_reqwidth()
        h = self.float_outer.winfo_reqheight()

        if initial:
            l, t, r, b = get_workarea()
            x = r - w - 8
            y = t + 220

        self.root.geometry(f"{w}x{h}+{x}+{y}")
        self.root.after(20, self.snap_to_edge)

    def show_panel(self):
        self.mode = "panel"

        x = self.root.winfo_x()
        y = self.root.winfo_y()

        self.float_outer.pack_forget()
        self.panel.pack(fill="both", expand=True)

        self._apply_window_flags(False)
        self.root.minsize(420, 260)
        self.root.geometry(f"420x280+{x}+{y}")
        self.root.lift()

    def _start_drag(self, e):
        self.drag_dx = e.x_root - self.root.winfo_x()
        self.drag_dy = e.y_root - self.root.winfo_y()

    def _on_drag(self, e):
        if self.mode != "float":
            return

        x = e.x_root - self.drag_dx
        y = e.y_root - self.drag_dy
        self.root.geometry(f"+{x}+{y}")

    def _end_drag(self, e):
        if self.mode == "float":
            self.snap_to_edge()

    def snap_to_edge(self):
        if self.mode != "float":
            return

        self.root.update_idletasks()

        hwnd = self.root.winfo_id()
        l, t, r, b = get_workarea(hwnd)

        w = self.root.winfo_width()
        h = self.root.winfo_height()

        x = self.root.winfo_x()
        y = self.root.winfo_y()
        cx = x + w / 2

        screen_mid = (l + r) / 2
        x = l if cx < screen_mid else r - w
        y = max(t, min(y, b - h))

        self.root.geometry(f"+{x}+{y}")

    def set_after_minutes(self):
        try:
            minutes = float(self.minutes_entry.get().strip())
            if minutes <= 0:
                raise ValueError
        except ValueError:
            self.detail_var.set("Invalid minutes.")
            return

        target = dt.datetime.now() + dt.timedelta(minutes=minutes)
        self._set_alarm(target)

    def set_at_time(self):
        text = self.time_entry.get().strip()

        try:
            parts = [int(x) for x in text.split(":")]

            if len(parts) == 2:
                hour, minute = parts
                second = 0
            elif len(parts) == 3:
                hour, minute, second = parts
            else:
                raise ValueError

            if not (0 <= hour <= 23 and 0 <= minute <= 59 and 0 <= second <= 59):
                raise ValueError

            now = dt.datetime.now()
            target = now.replace(
                hour=hour,
                minute=minute,
                second=second,
                microsecond=0,
            )

            if target <= now:
                target += dt.timedelta(days=1)

        except ValueError:
            self.detail_var.set("Invalid time. Use HH:MM or HH:MM:SS.")
            return

        self._set_alarm(target)

    def _set_alarm(self, target):
        self.target_time = target
        self.status_var.set("Alarm set")
        self.detail_var.set(f"Rings at {target:%Y-%m-%d %H:%M:%S}")
        self.show_float()

    def cancel_alarm(self):
        self.target_time = None
        self.status_var.set("No alarm")
        self.detail_var.set("Alarm cancelled.")

    def _tick(self):
        if self.target_time:
            remaining = int((self.target_time - dt.datetime.now()).total_seconds())

            if remaining <= 0:
                self.target_time = None
                self.status_var.set("Time's up")
                self.detail_var.set("Alarm triggered.")
                self._trigger_alarm()
            else:
                h = remaining // 3600
                m = remaining % 3600 // 60
                s = remaining % 60

                if h > 0:
                    self.status_var.set(f"{h:02d}:{m:02d}:{s:02d}")
                else:
                    self.status_var.set(f"{m:02d}:{s:02d}")

        self.root.after(500, self._tick)

    def _trigger_alarm(self):
        threading.Thread(target=self._beep, daemon=True).start()
        self._show_alarm_popup()

    def _beep(self):
        for _ in range(10):
            try:
                winsound.Beep(1000, 250)
            except RuntimeError:
                winsound.MessageBeep()
            time.sleep(0.15)

    def _show_alarm_popup(self):
        popup = tk.Toplevel(self.root)
        popup.title("Alarm")
        popup.configure(bg=self.BG)
        popup.resizable(False, False)
        popup.attributes("-topmost", True)

        box = tk.Frame(popup, bg=self.BG, padx=24, pady=20)
        box.pack(fill="both", expand=True)

        tk.Label(
            box,
            text="Time's up",
            bg=self.BG,
            fg=self.TEXT,
            font=(self.FONT, 18, "bold"),
        ).pack()

        tk.Label(
            box,
            text="Your alarm is ringing.",
            bg=self.BG,
            fg=self.MUTED,
            font=(self.FONT, 10),
        ).pack(pady=(6, 18))

        self._btn(box, "Dismiss", popup.destroy, bg=self.ACCENT_DARK, width=14).pack()

        popup.update_idletasks()
        w = popup.winfo_reqwidth()
        h = popup.winfo_reqheight()
        sw = popup.winfo_screenwidth()
        sh = popup.winfo_screenheight()

        popup.geometry(f"{w}x{h}+{(sw - w) // 2}+{(sh - h) // 2}")
        popup.lift()
        popup.focus_force()

    def close(self):
        self.root.destroy()

    def run(self):
        self.root.mainloop()


if __name__ == "__main__":
    _mutex_handle = acquire_single_instance_lock()
    FloatingAlarm().run()