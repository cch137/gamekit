"""
Auto Clicker with a draggable, semi-transparent floating overlay.

- No external dependencies: uses tkinter (bundled) + ctypes (Windows API).
- Clicks wherever the mouse cursor currently is, at the configured rate.
- Toggle clicking with the on-screen button or a user-configurable hotkey.
- Drag the window by its top grip bar. Close with the X button.
- Collapse to a small draggable icon with the "-" button; click the icon
  to expand back, or right-click it to close.
- Only one instance may run at a time.
"""

import ctypes
import sys
import threading
import time
import tkinter as tk

user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32

SINGLE_INSTANCE_MUTEX_NAME = "Global\\GameKit_AutoClicker_SingleInstance"
ERROR_ALREADY_EXISTS = 183


def _acquire_single_instance_lock():
    """Create a named mutex; if it already exists, another instance is
    running. Returns the mutex handle to keep it alive for the process
    lifetime (Windows releases it automatically on exit)."""
    handle = kernel32.CreateMutexW(None, False, SINGLE_INSTANCE_MUTEX_NAME)
    if kernel32.GetLastError() == ERROR_ALREADY_EXISTS:
        user32.MessageBoxW(None, "Auto Clicker is already running.",
                           "Auto Clicker", 0x40)  # MB_ICONINFORMATION
        sys.exit(0)
    return handle

# mouse_event flags
MOUSEEVENTF_LEFTDOWN = 0x0002
MOUSEEVENTF_LEFTUP = 0x0004
MOUSEEVENTF_RIGHTDOWN = 0x0008
MOUSEEVENTF_RIGHTUP = 0x0010

# Virtual-key code -> display name, for hotkey binding/display.
VK_NAMES = {0x08: "Backspace", 0x09: "Tab", 0x0D: "Enter", 0x1B: "Esc",
            0x20: "Space"}
for i in range(12):
    VK_NAMES[0x70 + i] = f"F{i + 1}"          # F1..F12
for c in range(0x30, 0x3A):
    VK_NAMES[c] = chr(c)                       # 0..9
for c in range(0x41, 0x5B):
    VK_NAMES[c] = chr(c)                       # A..Z
for i in range(10):
    VK_NAMES[0x60 + i] = f"Num{i}"             # numpad 0..9

# Keys we allow binding to (mouse buttons deliberately excluded).
BINDABLE_VKS = list(VK_NAMES.keys())


def click(button):
    if button == "right":
        down, up = MOUSEEVENTF_RIGHTDOWN, MOUSEEVENTF_RIGHTUP
    else:
        down, up = MOUSEEVENTF_LEFTDOWN, MOUSEEVENTF_LEFTUP
    user32.mouse_event(down, 0, 0, 0, 0)
    user32.mouse_event(up, 0, 0, 0, 0)


class AutoClicker:
    def __init__(self):
        self.running = False          # is a click loop active
        self.stop_flag = False        # app shutting down
        self.hotkey_vk = 0x75         # default F6
        self.listening = False        # capturing a new hotkey
        self.collapsed = False        # collapsed to a small icon
        self._build_ui()
        threading.Thread(target=self._click_loop, daemon=True).start()
        threading.Thread(target=self._hotkey_loop, daemon=True).start()

    def _build_ui(self):
        self.root = tk.Tk()
        self.root.overrideredirect(True)          # frameless
        self.root.attributes("-topmost", True)    # always on top
        self.root.attributes("-alpha", 0.85)      # semi-transparent
        self.root.configure(bg="#1e1e1e")
        self.root.geometry("+200+200")

        # main (expanded) view lives in its own frame so it can be swapped
        # out for the mini icon view when collapsed.
        self.main_frame = tk.Frame(self.root, bg="#1e1e1e")
        self.main_frame.pack(fill="both", expand=True)

        # top grip bar (drag handle)
        grip = tk.Frame(self.main_frame, bg="#3a3a3a", height=22, cursor="fleur")
        grip.pack(fill="x")
        collapse = tk.Label(grip, text="–", bg="#3a3a3a", fg="#dddddd",
                            font=("Segoe UI", 9, "bold"), cursor="hand2")
        collapse.pack(side="left", padx=6)
        collapse.bind("<Button-1>", lambda e: self._toggle_collapse())
        title = tk.Label(grip, text="Auto Clicker", bg="#3a3a3a", fg="#dddddd",
                         font=("Segoe UI", 9))
        title.pack(side="left")
        close = tk.Label(grip, text="X", bg="#3a3a3a", fg="#ff6b6b",
                         font=("Segoe UI", 9, "bold"), cursor="hand2")
        close.pack(side="right", padx=6)
        close.bind("<Button-1>", lambda e: self.quit())
        for w in (grip, title):
            w.bind("<Button-1>", self._start_drag)
            w.bind("<B1-Motion>", self._on_drag)

        body = tk.Frame(self.main_frame, bg="#1e1e1e")
        body.pack(fill="both", expand=True, padx=8, pady=6)

        # clicks-per-second + mouse button row
        row = tk.Frame(body, bg="#1e1e1e")
        row.pack(fill="x", pady=2)
        tk.Label(row, text="CPS:", bg="#1e1e1e", fg="#dddddd",
                 font=("Segoe UI", 9)).pack(side="left")
        self.cps_var = tk.StringVar(value="10")
        tk.Entry(row, textvariable=self.cps_var, width=6, justify="center").pack(
            side="left", padx=6)
        tk.Label(row, text="Btn:", bg="#1e1e1e", fg="#dddddd",
                 font=("Segoe UI", 9)).pack(side="left", padx=(8, 0))
        self.btn_var = tk.StringVar(value="left")
        tk.OptionMenu(row, self.btn_var, "left", "right").pack(side="left", padx=4)

        # hotkey row
        hk = tk.Frame(body, bg="#1e1e1e")
        hk.pack(fill="x", pady=2)
        tk.Label(hk, text="Hotkey:", bg="#1e1e1e", fg="#dddddd",
                 font=("Segoe UI", 9)).pack(side="left")
        self.hotkey_btn = tk.Button(hk, text=self._hotkey_name(), width=10,
                                    command=self._begin_listen, bg="#333333",
                                    fg="#dddddd", relief="flat",
                                    font=("Segoe UI", 9))
        self.hotkey_btn.pack(side="left", padx=6)

        # start/stop toggle
        self.toggle_btn = tk.Button(body, text="Start", width=22,
                                    command=self.toggle, bg="#2d7d46",
                                    fg="white", relief="flat",
                                    font=("Segoe UI", 9, "bold"))
        self.toggle_btn.pack(pady=(6, 0))
        self._refresh_toggle_text()

        # mini (collapsed) view: a small draggable icon, built but not
        # packed until the user collapses the window.
        self.mini_frame = tk.Frame(self.root, bg="#1e1e1e")
        self.mini_icon = tk.Label(self.mini_frame, text="AC", width=3,
                                  bg="#2d7d46", fg="white", cursor="fleur",
                                  font=("Segoe UI", 10, "bold"))
        self.mini_icon.pack(padx=2, pady=2)
        self.mini_icon.bind("<Button-1>", self._start_drag)
        self.mini_icon.bind("<B1-Motion>", self._on_drag)
        self.mini_icon.bind("<ButtonRelease-1>", self._end_drag)
        self.mini_icon.bind("<Button-3>", lambda e: self.quit())
        self._refresh_mini_icon()

    # --- collapse/expand ---
    def _toggle_collapse(self):
        self.collapsed = not self.collapsed
        x, y = self.root.winfo_x(), self.root.winfo_y()
        if self.collapsed:
            self.main_frame.pack_forget()
            self.mini_frame.pack(fill="both", expand=True)
        else:
            self.mini_frame.pack_forget()
            self.main_frame.pack(fill="both", expand=True)
        self.root.update_idletasks()
        w, h = self.root.winfo_reqwidth(), self.root.winfo_reqheight()
        self.root.geometry(f"{w}x{h}+{x}+{y}")

    def _refresh_mini_icon(self):
        self.mini_icon.config(bg="#a83232" if self.running else "#2d7d46")

    # --- dragging ---
    def _start_drag(self, e):
        self._dx, self._dy = e.x, e.y
        self._drag_moved = False

    def _on_drag(self, e):
        self._drag_moved = True
        x = self.root.winfo_pointerx() - self._dx
        y = self.root.winfo_pointery() - self._dy
        self.root.geometry(f"+{x}+{y}")

    def _end_drag(self, e):
        # a click (no movement) on the mini icon expands the window back
        if not self._drag_moved:
            self._toggle_collapse()

    # --- hotkey binding ---
    def _hotkey_name(self):
        return VK_NAMES.get(self.hotkey_vk, f"VK {self.hotkey_vk:#x}")

    def _begin_listen(self):
        self.listening = True
        self.hotkey_btn.config(text="press...", bg="#a86b32")

    def _set_hotkey(self, vk):
        self.hotkey_vk = vk
        self.listening = False
        self.hotkey_btn.config(text=self._hotkey_name(), bg="#333333")
        self._refresh_toggle_text()

    def _refresh_toggle_text(self):
        state = "Stop" if self.running else "Start"
        self.toggle_btn.config(text=f"{state} ({self._hotkey_name()})")

    # --- clicking ---
    def _get_interval(self):
        try:
            cps = float(self.cps_var.get())
            if cps <= 0:
                return None
            return 1.0 / min(cps, 200)   # cap at 200 cps for safety
        except ValueError:
            return None

    def toggle(self):
        self.running = not self.running
        if self.running:
            self.toggle_btn.config(bg="#a83232")
        else:
            self.toggle_btn.config(bg="#2d7d46")
        self._refresh_toggle_text()
        self._refresh_mini_icon()

    def _click_loop(self):
        while not self.stop_flag:
            if self.running:
                interval = self._get_interval()
                if interval is None:
                    time.sleep(0.1)
                    continue
                click(self.btn_var.get())
                time.sleep(interval)
            else:
                time.sleep(0.02)

    def _hotkey_loop(self):
        prev = False
        while not self.stop_flag:
            if self.listening:
                # capture the first bindable key that goes down
                for vk in BINDABLE_VKS:
                    if user32.GetAsyncKeyState(vk) & 0x8000:
                        self.root.after(0, self._set_hotkey, vk)
                        break
                time.sleep(0.03)
                continue
            pressed = bool(user32.GetAsyncKeyState(self.hotkey_vk) & 0x8000)
            if pressed and not prev:
                self.root.after(0, self.toggle)   # toggle on the UI thread
            prev = pressed
            time.sleep(0.03)

    def quit(self):
        self.stop_flag = True
        self.root.destroy()

    def run(self):
        self.root.mainloop()


if __name__ == "__main__":
    _mutex_handle = _acquire_single_instance_lock()
    AutoClicker().run()
