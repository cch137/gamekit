import ctypes
import datetime as dt
import itertools
import sys
import threading
import time
import tkinter as tk
from ctypes import wintypes
from typing import Literal

import winsound

user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32

MUTEX_NAME = "Global\\FloatingAlarm_SingleInstance"
ERROR_ALREADY_EXISTS = 183
MONITOR_DEFAULTTONEAREST = 2
DRAG_THRESHOLD = 6
QUICK_MINUTES = (5, 10, 15, 30, 60)


class MONITORINFO(ctypes.Structure):
    _fields_ = [
        ("cbSize", wintypes.DWORD),
        ("rcMonitor", wintypes.RECT),
        ("rcWork", wintypes.RECT),
        ("dwFlags", wintypes.DWORD),
    ]


class Theme:
    BG = "#1c1c1e"
    CARD = "#2c2c2e"
    CARD_2 = "#3a3a3c"
    BORDER = "#48484a"
    TEXT = "#f2f2f7"
    MUTED = "#8e8e93"
    ACCENT = "#8e9aaf"
    ACCENT_SOFT = "#636366"
    DANGER = "#ff453a"
    FONT = "Segoe UI"
    FLOAT_ALPHA = 0.72
    PANEL_ALPHA = 1.0
    INPUT_BG = "#141416"

    SCROLL_GUTTER = "#1c1c1e"
    SCROLL_TRACK = "#262629"
    SCROLL_THUMB = "#68686f"
    SCROLL_THUMB_ACTIVE = "#85858c"


def clamp(value, lo, hi):
    return max(lo, min(value, hi))


class SlimVerticalScrollbar(tk.Canvas):
    def __init__(self, parent, command=None, width=14):
        super().__init__(
            parent,
            width=width,
            bg=Theme.SCROLL_GUTTER,
            highlightthickness=0,
            bd=0,
            relief="flat",
            cursor="arrow",
        )
        self.command = command
        self.first = 0.0
        self.last = 1.0
        self._dragging = False
        self._hover = False
        self._drag_offset = 0
        self._thumb_top = 0
        self._thumb_bottom = 0

        self.bind("<Configure>", lambda _e: self._draw())
        self.bind("<Button-1>", self._on_press)
        self.bind("<B1-Motion>", self._on_drag)
        self.bind("<ButtonRelease-1>", self._on_release)
        self.bind("<Motion>", self._on_motion)
        self.bind("<Leave>", self._on_leave)

    def set(self, first, last):
        self.first = clamp(float(first), 0.0, 1.0)
        self.last = clamp(float(last), 0.0, 1.0)
        self._draw()

    def _rounded_rect(self, x1, y1, x2, y2, radius, fill, tag):
        radius = max(1, min(radius, int((x2 - x1) / 2), int((y2 - y1) / 2)))
        self.create_rectangle(x1 + radius, y1, x2 - radius, y2, fill=fill, outline="", tags=tag)
        self.create_rectangle(x1, y1 + radius, x2, y2 - radius, fill=fill, outline="", tags=tag)
        self.create_oval(x1, y1, x1 + radius * 2, y1 + radius * 2, fill=fill, outline="", tags=tag)
        self.create_oval(x2 - radius * 2, y1, x2, y1 + radius * 2, fill=fill, outline="", tags=tag)
        self.create_oval(x1, y2 - radius * 2, x1 + radius * 2, y2, fill=fill, outline="", tags=tag)
        self.create_oval(x2 - radius * 2, y2 - radius * 2, x2, y2, fill=fill, outline="", tags=tag)

    def _metrics(self):
        w = max(1, self.winfo_width())
        h = max(1, self.winfo_height())

        pad_y = 12
        track_h = max(1, h - pad_y * 2)
        visible = clamp(self.last - self.first, 0.0, 1.0)

        if visible >= 0.999:
            return None

        thumb_h = int(track_h * visible)
        thumb_h = clamp(thumb_h, 44, track_h)

        movable = max(1, track_h - thumb_h)
        top = pad_y + int(movable * (self.first / max(0.0001, 1.0 - visible)))
        top = clamp(top, pad_y, pad_y + movable)

        return {
            "w": w,
            "h": h,
            "pad_y": pad_y,
            "track_h": track_h,
            "visible": visible,
            "thumb_h": thumb_h,
            "movable": movable,
            "top": top,
            "bottom": top + thumb_h,
        }

    def _draw(self):
        self.delete("all")
        m = self._metrics()
        if not m:
            return

        w = m["w"]
        pad_y = m["pad_y"]
        track_bottom = pad_y + m["track_h"]

        track_w = 3
        thumb_w = 6

        track_x1 = (w - track_w) // 2
        track_x2 = track_x1 + track_w

        thumb_x1 = (w - thumb_w) // 2
        thumb_x2 = thumb_x1 + thumb_w

        self._thumb_top = m["top"]
        self._thumb_bottom = m["bottom"]

        self._rounded_rect(
            track_x1,
            pad_y,
            track_x2,
            track_bottom,
            2,
            Theme.SCROLL_TRACK,
            "track",
        )

        thumb_color = (
            Theme.SCROLL_THUMB_ACTIVE
            if self._dragging or self._hover
            else Theme.SCROLL_THUMB
        )

        self._rounded_rect(
            thumb_x1,
            self._thumb_top,
            thumb_x2,
            self._thumb_bottom,
            3,
            thumb_color,
            "thumb",
        )

    def _on_press(self, event):
        m = self._metrics()
        if not m:
            return

        if self._thumb_top <= event.y <= self._thumb_bottom:
            self._dragging = True
            self._drag_offset = event.y - self._thumb_top
            self._draw()
            return

        if self.command:
            direction = -1 if event.y < self._thumb_top else 1
            self.command("scroll", direction, "pages")

    def _on_drag(self, event):
        if not self._dragging or not self.command:
            return

        m = self._metrics()
        if not m:
            return

        top = clamp(
            event.y - self._drag_offset,
            m["pad_y"],
            m["pad_y"] + m["movable"],
        )
        fraction = (top - m["pad_y"]) / m["movable"]
        self.command("moveto", fraction * (1.0 - m["visible"]))

    def _on_release(self, _event):
        self._dragging = False
        self._draw()

    def _on_motion(self, event):
        was_hover = self._hover
        self._hover = self._thumb_top <= event.y <= self._thumb_bottom
        if self._hover != was_hover:
            self._draw()

    def _on_leave(self, _event):
        if self._hover:
            self._hover = False
            self._draw()


class Alarm:
    __slots__ = ("id", "name", "target")

    def __init__(self, alarm_id, name, target):
        self.id = alarm_id
        self.name = name
        self.target = target


def acquire_single_instance_lock():
    kernel32.CreateMutexW.restype = wintypes.HANDLE
    handle = kernel32.CreateMutexW(None, False, MUTEX_NAME)
    if kernel32.GetLastError() == ERROR_ALREADY_EXISTS:
        user32.MessageBoxW(
            None,
            "Floating Alarm is already running.",
            "Floating Alarm",
            0x40,
        )
        sys.exit(0)
    return handle


def set_dark_title_bar(hwnd: int, enabled: bool = True):
    if not hwnd:
        return
    try:
        value = ctypes.c_int(1 if enabled else 0)
        for attr in (20, 19):
            hr = ctypes.windll.dwmapi.DwmSetWindowAttribute(
                wintypes.HWND(int(hwnd)),
                attr,
                ctypes.byref(value),
                ctypes.sizeof(value),
            )
            if hr == 0:
                break
    except Exception:
        pass


def get_workarea_from_point(x, y):
    point = wintypes.POINT(int(x), int(y))
    monitor = user32.MonitorFromPoint(point, MONITOR_DEFAULTTONEAREST)
    info = MONITORINFO()
    info.cbSize = ctypes.sizeof(MONITORINFO)
    if monitor and user32.GetMonitorInfoW(monitor, ctypes.byref(info)):
        r = info.rcWork
        return r.left, r.top, r.right, r.bottom
    return 0, 0, user32.GetSystemMetrics(0), user32.GetSystemMetrics(1)


def get_workarea():
    return 0, 0, user32.GetSystemMetrics(0), user32.GetSystemMetrics(1)


class FloatingAlarm:
    def __init__(self):
        self.alarms = []
        self._id_seq = itertools.count(1)
        self._ringing_ids = set()

        self.mode = "panel"
        self.float_xy = None
        self.drag_dx = 0
        self.drag_dy = 0
        self.drag_start = (0, 0)
        self.dragging = False

        self.countdown_minutes = 10

        now = dt.datetime.now()
        self.at_hour = now.hour
        self.at_minute = (now.minute // 5 + 1) * 5
        if self.at_minute >= 60:
            self.at_hour = (self.at_hour + 1) % 24
            self.at_minute = 0

        self.root = tk.Tk()
        self.root.title("Floating Alarm")
        self.root.configure(bg=Theme.BG)
        self.root.protocol("WM_DELETE_WINDOW", self._on_window_close)
        self.root.withdraw()

        self.status_var = tk.StringVar(value="No alarm")
        self.detail_var = tk.StringVar(value="Set an alarm below")
        self.countdown_var = tk.StringVar(value=str(self.countdown_minutes))
        self.hour_var = tk.StringVar(value=f"{self.at_hour:02d}")
        self.minute_var = tk.StringVar(value=f"{self.at_minute:02d}")
        self.minutes_entry_var = tk.StringVar(value=str(self.countdown_minutes))
        self.time_entry_var = tk.StringVar(value=f"{self.at_hour:02d}:{self.at_minute:02d}")
        self.name_var = tk.StringVar(value="Alarm")
        self.at_preview_var = tk.StringVar(value="")

        self._build_float_ui()
        self._build_panel_ui()
        self._refresh_at_preview()
        self._refresh_alarm_list()

        self.show_panel()
        self._tick()

    def _apply_dark_title_bar(self):
        self.root.update_idletasks()
        hwnd = None
        try:
            frame = self.root.wm_frame()
            if frame:
                hwnd = int(frame, 16)
        except Exception:
            hwnd = None
        if not hwnd:
            try:
                hwnd = int(self.root.winfo_id())
            except Exception:
                return
        set_dark_title_bar(hwnd, True)

    def _btn(self, parent, text, command, bg=None, fg=None, padx=14, pady=8):
        return tk.Button(
            parent,
            text=text,
            command=command,
            bg=bg or Theme.CARD_2,
            fg=fg or Theme.TEXT,
            activebackground=Theme.BORDER,
            activeforeground=Theme.TEXT,
            relief="flat",
            bd=0,
            padx=padx,
            pady=pady,
            cursor="hand2",
            font=(Theme.FONT, 9, "bold"),
            highlightthickness=0,
        )

    def _chip(self, parent, text, command):
        return tk.Button(
            parent,
            text=text,
            command=command,
            bg=Theme.CARD,
            fg=Theme.TEXT,
            activebackground=Theme.BORDER,
            activeforeground=Theme.TEXT,
            relief="flat",
            bd=0,
            padx=12,
            pady=6,
            cursor="hand2",
            font=(Theme.FONT, 9),
            highlightthickness=1,
            highlightbackground=Theme.BORDER,
            highlightcolor=Theme.ACCENT,
        )

    def _entry(
        self,
        parent,
        textvariable,
        width=8,
        justify: Literal["left", "center", "right"] = "center",
    ):
        return tk.Entry(
            parent,
            textvariable=textvariable,
            width=width,
            bg=Theme.INPUT_BG,
            fg=Theme.TEXT,
            insertbackground=Theme.TEXT,
            relief="flat",
            highlightthickness=1,
            highlightbackground=Theme.BORDER,
            highlightcolor=Theme.ACCENT,
            font=(Theme.FONT, 11),
            justify=justify,
        )

    def _stepper(self, parent, textvariable, on_minus, on_plus, width=4):
        box = tk.Frame(
            parent,
            bg=Theme.CARD,
            highlightthickness=1,
            highlightbackground=Theme.BORDER,
        )
        self._btn(box, "−", on_minus, bg=Theme.CARD, padx=10, pady=6).pack(side="left")
        tk.Label(
            box,
            textvariable=textvariable,
            bg=Theme.CARD,
            fg=Theme.TEXT,
            font=(Theme.FONT, 16, "bold"),
            width=width,
        ).pack(side="left", padx=4)
        self._btn(box, "+", on_plus, bg=Theme.CARD, padx=10, pady=6).pack(side="left")
        return box

    def _section_label(self, parent, text):
        return tk.Label(
            parent,
            text=text,
            bg=Theme.BG,
            fg=Theme.MUTED,
            font=(Theme.FONT, 9),
            anchor="w",
        )

    def _build_float_ui(self):
        self.float_outer = tk.Frame(self.root, bg=Theme.CARD)
        self.float_card = tk.Frame(self.float_outer, bg=Theme.CARD, padx=14, pady=12)
        self.float_card.pack()

        self.float_icon = tk.Label(
            self.float_card,
            text="⏰",
            bg=Theme.CARD,
            fg=Theme.ACCENT,
            font=(Theme.FONT, 20),
        )
        self.float_icon.pack()

        self.float_status = tk.Label(
            self.float_card,
            textvariable=self.status_var,
            bg=Theme.CARD,
            fg=Theme.TEXT,
            font=(Theme.FONT, 9, "bold"),
        )
        self.float_status.pack(pady=(2, 0))

        for w in (
            self.float_outer,
            self.float_card,
            self.float_icon,
            self.float_status,
        ):
            w.bind("<Button-1>", self._start_drag)
            w.bind("<B1-Motion>", self._on_drag)
            w.bind("<ButtonRelease-1>", self._end_drag)
            w.bind("<Button-3>", lambda _e: self.quit_app())

    def _build_panel_ui(self):
        self.panel = tk.Frame(self.root, bg=Theme.BG)

        self.panel_canvas = tk.Canvas(
            self.panel,
            bg=Theme.BG,
            highlightthickness=0,
            bd=0,
            yscrollincrement=32,
        )

        self.panel_scroll = SlimVerticalScrollbar(
            self.panel,
            command=self.panel_canvas.yview,
            width=14,
        )

        self.panel_canvas.configure(yscrollcommand=self.panel_scroll.set)

        self.panel_scroll.pack(side="right", fill="y")
        self.panel_canvas.pack(side="left", fill="both", expand=True)

        self.panel_inner = tk.Frame(self.panel_canvas, bg=Theme.BG, padx=22, pady=18)
        self._panel_window = self.panel_canvas.create_window(
            (0, 0),
            window=self.panel_inner,
            anchor="nw",
        )

        self.panel_inner.bind("<Configure>", self._on_panel_inner_configure)
        self.panel_canvas.bind("<Configure>", self._on_panel_canvas_configure)
        self.panel_canvas.bind_all("<MouseWheel>", self._on_mousewheel)

        header = tk.Frame(self.panel_inner, bg=Theme.BG)
        header.pack(fill="x")
        tk.Label(
            header,
            text="Alarm",
            bg=Theme.BG,
            fg=Theme.TEXT,
            font=(Theme.FONT, 18, "bold"),
        ).pack(side="left")

        status_box = tk.Frame(self.panel_inner, bg=Theme.CARD, padx=14, pady=12)
        status_box.pack(fill="x", pady=(16, 12))

        tk.Label(
            status_box,
            textvariable=self.status_var,
            bg=Theme.CARD,
            fg=Theme.TEXT,
            font=(Theme.FONT, 14, "bold"),
            anchor="w",
        ).pack(fill="x")
        tk.Label(
            status_box,
            textvariable=self.detail_var,
            bg=Theme.CARD,
            fg=Theme.MUTED,
            font=(Theme.FONT, 9),
            anchor="w",
        ).pack(fill="x", pady=(4, 0))

        self._section_label(self.panel_inner, "NAME").pack(fill="x", pady=(4, 6))
        name_wrap = tk.Frame(
            self.panel_inner,
            bg=Theme.INPUT_BG,
            highlightthickness=1,
            highlightbackground=Theme.BORDER,
            highlightcolor=Theme.ACCENT,
        )
        name_wrap.pack(fill="x")
        name_entry = self._entry(name_wrap, self.name_var, width=28, justify="left")
        name_entry.configure(highlightthickness=0, bd=0)
        name_entry.pack(fill="x", padx=10, pady=8)

        self._section_label(self.panel_inner, "COUNTDOWN").pack(fill="x", pady=(14, 6))

        quick = tk.Frame(self.panel_inner, bg=Theme.BG)
        quick.pack(fill="x")
        for m in QUICK_MINUTES:
            label = f"{m}m" if m < 60 else "1h"
            self._chip(quick, label, lambda m=m: self._quick_countdown(m)).pack(
                side="left", padx=(0, 6)
            )

        custom = tk.Frame(self.panel_inner, bg=Theme.BG)
        custom.pack(fill="x", pady=(10, 0))

        self._stepper(
            custom,
            self.countdown_var,
            self._dec_minutes,
            self._inc_minutes,
            width=4,
        ).pack(side="left")
        tk.Label(
            custom,
            text="min",
            bg=Theme.BG,
            fg=Theme.MUTED,
            font=(Theme.FONT, 10),
        ).pack(side="left", padx=(8, 10))
        self._entry(custom, self.minutes_entry_var, width=6).pack(side="left")
        self._btn(
            custom,
            "Start",
            self.set_after_minutes,
            bg=Theme.ACCENT_SOFT,
            padx=16,
            pady=8,
        ).pack(side="left", padx=(10, 0))

        self._section_label(self.panel_inner, "RING AT").pack(fill="x", pady=(16, 6))

        at_row = tk.Frame(self.panel_inner, bg=Theme.BG)
        at_row.pack(fill="x")

        self._stepper(
            at_row,
            self.hour_var,
            self._dec_hour,
            self._inc_hour,
            width=3,
        ).pack(side="left")
        tk.Label(
            at_row,
            text=":",
            bg=Theme.BG,
            fg=Theme.TEXT,
            font=(Theme.FONT, 16, "bold"),
        ).pack(side="left", padx=6)
        self._stepper(
            at_row,
            self.minute_var,
            self._dec_minute,
            self._inc_minute,
            width=3,
        ).pack(side="left")
        self._entry(at_row, self.time_entry_var, width=7).pack(side="left", padx=(12, 0))
        self._btn(
            at_row,
            "Set",
            self.set_at_time,
            bg=Theme.ACCENT_SOFT,
            padx=16,
            pady=8,
        ).pack(side="left", padx=(10, 0))

        tk.Label(
            self.panel_inner,
            textvariable=self.at_preview_var,
            bg=Theme.BG,
            fg=Theme.MUTED,
            font=(Theme.FONT, 9),
            anchor="w",
        ).pack(fill="x", pady=(8, 0))

        self._section_label(self.panel_inner, "ACTIVE").pack(fill="x", pady=(16, 6))
        self.alarm_list = tk.Frame(self.panel_inner, bg=Theme.BG)
        self.alarm_list.pack(fill="x")

        footer = tk.Frame(self.panel_inner, bg=Theme.BG)
        footer.pack(fill="x", pady=(18, 0))

        self._btn(
            footer,
            "Cancel All",
            self.cancel_all_alarms,
            bg=Theme.CARD_2,
            padx=14,
            pady=8,
        ).pack(side="left")

        self._btn(
            footer,
            "Quit",
            self.quit_app,
            bg=Theme.DANGER,
            fg="white",
            padx=14,
            pady=8,
        ).pack(side="right")

    def _on_panel_inner_configure(self, _event=None):
        self._sync_scroll_region()

    def _on_panel_canvas_configure(self, _event=None):
        self._sync_scroll_region()

    def _sync_scroll_region(self):
        try:
            self.panel_canvas.update_idletasks()
            canvas_w = max(1, self.panel_canvas.winfo_width())
            canvas_h = max(1, self.panel_canvas.winfo_height())
            content_h = max(1, self.panel_inner.winfo_reqheight())

            self.panel_canvas.itemconfigure(self._panel_window, width=canvas_w)
            self.panel_canvas.configure(scrollregion=(0, 0, canvas_w, content_h))

            if content_h <= canvas_h:
                self.panel_canvas.yview_moveto(0)
                self.panel_scroll.set(0, 1)
                return

            first, _last = self.panel_canvas.yview()
            max_first = max(0.0, 1.0 - canvas_h / content_h)
            if first > max_first:
                self.panel_canvas.yview_moveto(max_first)
        except tk.TclError:
            pass

    def _on_mousewheel(self, event):
        if self.mode != "panel":
            return

        if self.panel_inner.winfo_reqheight() <= self.panel_canvas.winfo_height():
            self.panel_canvas.yview_moveto(0)
            return "break"

        direction = -1 if event.delta > 0 else 1
        self.panel_canvas.yview_scroll(direction, "units")
        return "break"

    def _sync_countdown_fields(self):
        text = (
            str(int(self.countdown_minutes))
            if float(self.countdown_minutes).is_integer()
            else str(self.countdown_minutes)
        )
        self.countdown_var.set(text)
        self.minutes_entry_var.set(text)

    def _sync_time_fields(self):
        self.hour_var.set(f"{self.at_hour:02d}")
        self.minute_var.set(f"{self.at_minute:02d}")
        self.time_entry_var.set(f"{self.at_hour:02d}:{self.at_minute:02d}")
        self._refresh_at_preview()

    def _inc_minutes(self):
        self.countdown_minutes = clamp(int(self.countdown_minutes) + 1, 1, 24 * 60)
        self._sync_countdown_fields()

    def _dec_minutes(self):
        self.countdown_minutes = clamp(int(self.countdown_minutes) - 1, 1, 24 * 60)
        self._sync_countdown_fields()

    def _inc_hour(self):
        self.at_hour = (self.at_hour + 1) % 24
        self._sync_time_fields()

    def _dec_hour(self):
        self.at_hour = (self.at_hour - 1) % 24
        self._sync_time_fields()

    def _inc_minute(self):
        self.at_minute = (self.at_minute + 1) % 60
        self._sync_time_fields()

    def _dec_minute(self):
        self.at_minute = (self.at_minute - 1) % 60
        self._sync_time_fields()

    def _refresh_at_preview(self):
        now = dt.datetime.now()
        target = now.replace(
            hour=self.at_hour,
            minute=self.at_minute,
            second=0,
            microsecond=0,
        )
        if target <= now:
            target += dt.timedelta(days=1)
            day = "Tomorrow"
        else:
            day = "Today"
        self.at_preview_var.set(f"{day} · {target:%H:%M}")

    def _alarm_name(self):
        name = self.name_var.get().strip()
        return name or "Alarm"

    def _refresh_alarm_list(self):
        for child in self.alarm_list.winfo_children():
            child.destroy()

        if not self.alarms:
            tk.Label(
                self.alarm_list,
                text="No active alarms",
                bg=Theme.BG,
                fg=Theme.MUTED,
                font=(Theme.FONT, 9),
                anchor="w",
            ).pack(fill="x")
            self.root.after_idle(self._sync_scroll_region)
            return

        for alarm in sorted(self.alarms, key=lambda a: a.target):
            row = tk.Frame(self.alarm_list, bg=Theme.CARD, padx=10, pady=8)
            row.pack(fill="x", pady=(0, 6))

            left = tk.Frame(row, bg=Theme.CARD)
            left.pack(side="left", fill="x", expand=True)

            tk.Label(
                left,
                text=alarm.name,
                bg=Theme.CARD,
                fg=Theme.TEXT,
                font=(Theme.FONT, 10, "bold"),
                anchor="w",
            ).pack(fill="x")
            tk.Label(
                left,
                text=f"Rings at {alarm.target:%H:%M} · {alarm.target:%b %d}",
                bg=Theme.CARD,
                fg=Theme.MUTED,
                font=(Theme.FONT, 8),
                anchor="w",
            ).pack(fill="x", pady=(2, 0))

            self._btn(
                row,
                "Cancel",
                lambda a=alarm: self.cancel_alarm(a.id),
                bg=Theme.CARD_2,
                padx=10,
                pady=4,
            ).pack(side="right")

        self.root.after_idle(self._sync_scroll_region)

    def _remember_float_pos(self):
        try:
            self.float_xy = (self.root.winfo_x(), self.root.winfo_y())
        except tk.TclError:
            pass

    def _ensure_default_float_xy(self, w=80, h=80):
        if self.float_xy:
            return
        l, t, r, b = get_workarea()
        try:
            pt = wintypes.POINT()
            user32.GetCursorPos(ctypes.byref(pt))
            l, t, r, b = get_workarea_from_point(pt.x, pt.y)
        except Exception:
            pass
        self.float_xy = (r - w - 12, t + 200)

    def _anchor_point(self):
        if self.float_xy:
            return self.float_xy
        try:
            return self.root.winfo_x(), self.root.winfo_y()
        except tk.TclError:
            return 0, 0

    def _center_geometry(self, w, h):
        ax, ay = self._anchor_point()
        if ax == 0 and ay == 0 and not self.float_xy:
            try:
                pt = wintypes.POINT()
                user32.GetCursorPos(ctypes.byref(pt))
                ax, ay = pt.x, pt.y
            except Exception:
                pass
        l, t, r, b = get_workarea_from_point(ax, ay)
        x = l + max(0, (r - l - w) // 2)
        y = t + max(0, (b - t - h) // 2)
        return x, y

    def _fit_panel_size(self):
        self.root.update_idletasks()
        req_w = max(self.panel_inner.winfo_reqwidth() + 32, 500)
        req_h = 640
        self.root.minsize(480, 480)
        return req_w, req_h

    def _prepare_window(self, floating):
        self.root.withdraw()
        self.root.overrideredirect(bool(floating))
        self.root.attributes("-topmost", bool(floating))
        self.root.attributes(
            "-alpha",
            Theme.FLOAT_ALPHA if floating else Theme.PANEL_ALPHA,
        )
        self.root.resizable(not floating, not floating)

    def show_float(self, initial=False):
        self.mode = "float"
        self._prepare_window(True)

        self.panel.pack_forget()
        self.float_outer.pack()

        self.root.minsize(1, 1)
        self.root.update_idletasks()

        w = max(self.float_outer.winfo_reqwidth(), 72)
        h = max(self.float_outer.winfo_reqheight(), 72)

        self._ensure_default_float_xy(w, h)
        x, y = self.float_xy

        l, t, r, b = get_workarea_from_point(x + w // 2, y + h // 2)
        x = l if (x + w / 2) < (l + r) / 2 else r - w
        y = clamp(y, t, b - h)
        self.float_xy = (x, y)

        self.root.geometry(f"{w}x{h}+{x}+{y}")
        self.root.deiconify()
        self.root.update_idletasks()
        self.snap_to_edge()

    def show_panel(self):
        if self.mode == "float":
            self._remember_float_pos()

        self.mode = "panel"
        self._refresh_at_preview()
        self._refresh_alarm_list()
        self.minutes_entry_var.set(
            str(int(self.countdown_minutes))
            if float(self.countdown_minutes).is_integer()
            else str(self.countdown_minutes)
        )
        self.time_entry_var.set(f"{self.at_hour:02d}:{self.at_minute:02d}")
        if not self.name_var.get().strip():
            self.name_var.set("Alarm")

        self._prepare_window(False)
        self.float_outer.pack_forget()
        self.panel.pack(fill="both", expand=True)

        w, h = self._fit_panel_size()
        x, y = self._center_geometry(w, h)
        self.root.geometry(f"{w}x{h}+{x}+{y}")
        self.root.deiconify()
        self._apply_dark_title_bar()
        self.root.lift()
        self.root.focus_force()
        self.panel_canvas.yview_moveto(0)
        self.root.after_idle(self._sync_scroll_region)

        def _nudge():
            if self.mode != "panel":
                return
            w2, h2 = self._fit_panel_size()
            x2, y2 = self._center_geometry(w2, h2)
            try:
                cx, cy = self.root.winfo_x(), self.root.winfo_y()
                cw, ch = self.root.winfo_width(), self.root.winfo_height()
            except tk.TclError:
                return
            if (
                abs(cx - x2) > 2
                or abs(cy - y2) > 2
                or abs(cw - w2) > 2
                or abs(ch - h2) > 2
            ):
                self.root.geometry(f"{w2}x{h2}+{x2}+{y2}")
            self._apply_dark_title_bar()
            self.panel_canvas.yview_moveto(0)
            self._sync_scroll_region()

        self.root.after(1, _nudge)

    def _start_drag(self, e):
        self.drag_dx = e.x_root - self.root.winfo_x()
        self.drag_dy = e.y_root - self.root.winfo_y()
        self.drag_start = (e.x_root, e.y_root)
        self.dragging = False

    def _on_drag(self, e):
        if self.mode != "float":
            return
        if (
            abs(e.x_root - self.drag_start[0]) > DRAG_THRESHOLD
            or abs(e.y_root - self.drag_start[1]) > DRAG_THRESHOLD
        ):
            self.dragging = True
        if self.dragging:
            self.root.geometry(f"+{e.x_root - self.drag_dx}+{e.y_root - self.drag_dy}")

    def _end_drag(self, e):
        if self.mode != "float":
            return
        if self.dragging:
            self.snap_to_edge()
            self._remember_float_pos()
        else:
            self.show_panel()

    def snap_to_edge(self):
        if self.mode != "float":
            return
        self.root.update_idletasks()
        x, y = self.root.winfo_x(), self.root.winfo_y()
        w, h = self.root.winfo_width(), self.root.winfo_height()
        l, t, r, b = get_workarea_from_point(x + w // 2, y + h // 2)
        x = l if (x + w / 2) < (l + r) / 2 else r - w
        y = clamp(y, t, b - h)
        self.root.geometry(f"+{x}+{y}")
        self.float_xy = (x, y)

    def _next_alarm(self):
        if not self.alarms:
            return None
        return min(self.alarms, key=lambda a: a.target)

    def _quick_countdown(self, minutes):
        self.countdown_minutes = minutes
        self._sync_countdown_fields()
        self.set_after_minutes()

    def set_after_minutes(self):
        raw = self.minutes_entry_var.get().strip()
        try:
            minutes = float(raw) if raw else float(self.countdown_minutes)
            if minutes <= 0:
                raise ValueError
        except ValueError:
            self.detail_var.set("Invalid minutes.")
            return

        self.countdown_minutes = int(minutes) if float(minutes).is_integer() else minutes
        self._sync_countdown_fields()
        self._add_alarm(dt.datetime.now() + dt.timedelta(minutes=float(minutes)))

    def set_at_time(self):
        raw = self.time_entry_var.get().strip()
        try:
            if raw:
                parts = [int(x) for x in raw.split(":")]
                if len(parts) == 2:
                    hour, minute = parts
                    second = 0
                elif len(parts) == 3:
                    hour, minute, second = parts
                else:
                    raise ValueError
            else:
                hour, minute, second = self.at_hour, self.at_minute, 0

            if not (0 <= hour <= 23 and 0 <= minute <= 59 and 0 <= second <= 59):
                raise ValueError
        except ValueError:
            self.detail_var.set("Invalid time. Use HH:MM")
            return

        self.at_hour, self.at_minute = hour, minute
        self._sync_time_fields()

        now = dt.datetime.now()
        target = now.replace(hour=hour, minute=minute, second=second, microsecond=0)
        if target <= now:
            target += dt.timedelta(days=1)
        self._add_alarm(target)

    def _add_alarm(self, target):
        alarm = Alarm(next(self._id_seq), self._alarm_name(), target)
        self.alarms.append(alarm)
        self._update_status_text()
        self._refresh_alarm_list()
        self.name_var.set("Alarm")
        if self.mode == "panel":
            self.root.after_idle(self._sync_scroll_region)

    def cancel_alarm(self, alarm_id):
        self.alarms = [a for a in self.alarms if a.id != alarm_id]
        self._update_status_text()
        self._refresh_alarm_list()

    def cancel_all_alarms(self):
        self.alarms.clear()
        self.status_var.set("No alarm")
        self.detail_var.set("All alarms cancelled")
        self.panel_canvas.yview_moveto(0)
        self._refresh_alarm_list()

    def _format_countdown(self, remaining):
        h = remaining // 3600
        m = (remaining % 3600) // 60
        s = remaining % 60
        if h > 0:
            return f"{h:02d}:{m:02d}:{s:02d}"
        return f"{m:02d}:{s:02d}"

    def _update_status_text(self):
        nxt = self._next_alarm()
        if not nxt:
            if self.status_var.get() != "Time's up":
                self.status_var.set("No alarm")
                if self.detail_var.get() != "All alarms cancelled":
                    self.detail_var.set("Set an alarm below")
            return

        remaining = int((nxt.target - dt.datetime.now()).total_seconds())
        if remaining < 0:
            remaining = 0
        self.status_var.set(self._format_countdown(remaining))

        extra = len(self.alarms) - 1
        if extra > 0:
            self.detail_var.set(
                f"{nxt.name} · Rings at {nxt.target:%H:%M} · +{extra} more"
            )
        else:
            self.detail_var.set(f"{nxt.name} · Rings at {nxt.target:%H:%M}")

    def _tick(self):
        now = dt.datetime.now()
        due = [a for a in self.alarms if a.target <= now]

        if due:
            for alarm in due:
                if alarm.id in self._ringing_ids:
                    continue
                self._ringing_ids.add(alarm.id)
                self._trigger_alarm(alarm)

            due_ids = {a.id for a in due}
            self.alarms = [a for a in self.alarms if a.id not in due_ids]

            if self.mode == "panel":
                self._refresh_alarm_list()

        self._update_status_text()
        self.root.after(500, self._tick)

    def _trigger_alarm(self, alarm):
        self.status_var.set("Time's up")
        self.detail_var.set(alarm.name)
        threading.Thread(target=self._beep, daemon=True).start()
        self._show_alarm_popup(alarm)

    def _beep(self):
        melody = (523, 659, 784)
        try:
            for _ in range(3):
                for freq in melody:
                    winsound.Beep(freq, 220)
                    time.sleep(0.04)
                time.sleep(0.45)
            return
        except RuntimeError:
            pass

        for _ in range(4):
            try:
                winsound.MessageBeep(winsound.MB_ICONASTERISK)
            except Exception:
                try:
                    winsound.PlaySound(
                        "SystemNotification",
                        winsound.SND_ALIAS | winsound.SND_ASYNC,
                    )
                except Exception:
                    break
            time.sleep(0.7)

    def _show_alarm_popup(self, alarm):
        popup = tk.Toplevel(self.root)
        popup.title(alarm.name)
        popup.configure(bg=Theme.BG)
        popup.resizable(False, False)
        popup.attributes("-topmost", True)
        popup.withdraw()
        popup.overrideredirect(True)

        shell = tk.Frame(popup, bg=Theme.BORDER, padx=1, pady=1)
        shell.pack(fill="both", expand=True)
        box = tk.Frame(shell, bg=Theme.BG, padx=28, pady=24)
        box.pack(fill="both", expand=True)

        tk.Label(
            box,
            text="Time's up",
            bg=Theme.BG,
            fg=Theme.TEXT,
            font=(Theme.FONT, 18, "bold"),
        ).pack()
        tk.Label(
            box,
            text=alarm.name,
            bg=Theme.BG,
            fg=Theme.MUTED,
            font=(Theme.FONT, 11),
        ).pack(pady=(6, 18))

        def dismiss():
            self._ringing_ids.discard(alarm.id)
            popup.destroy()
            self._update_status_text()

        self._btn(box, "Dismiss", dismiss, bg=Theme.ACCENT_SOFT, padx=20, pady=8).pack()

        popup.update_idletasks()
        w, h = popup.winfo_reqwidth(), popup.winfo_reqheight()
        ax, ay = self._anchor_point()
        l, t, r, b = get_workarea_from_point(ax, ay)
        popup.geometry(f"{w}x{h}+{l + (r - l - w) // 2}+{t + (b - t - h) // 2}")
        popup.deiconify()
        popup.lift()
        popup.focus_force()
        popup.protocol("WM_DELETE_WINDOW", dismiss)

    def _on_window_close(self):
        if self.mode == "panel":
            self.show_float()
        else:
            self.quit_app()

    def quit_app(self):
        try:
            self.panel_canvas.unbind_all("<MouseWheel>")
        except tk.TclError:
            pass
        self.root.destroy()

    def run(self):
        self.root.mainloop()


if __name__ == "__main__":
    _mutex_handle = acquire_single_instance_lock()
    FloatingAlarm().run()