# -*- coding: utf-8 -*-
"""
Created on Wed May 27 09:36:52 2026

@author: carst
"""

import tkinter as tk
from tkinter import font
import time
import random

# Configurable timings (ms)
DEBOUNCE_MS = 10
LONG_PRESS_MS = 800
REPEAT_START_MS = 300
REPEAT_INTERVAL_MS = 100
MASK_DELAY_MS = 400
INACTIVITY_TIMEOUT_MS = 30_000
LOCKOUT_DURATION_MS = 30_000
MAX_ATTEMPTS = 3

def random_pin():
    return [random.randint(0,9) for _ in range(4)]

class PinSimulator(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("PIN Eingabe Simulation - Cursor Tasten")
        self.resizable(False, False)
        self.geometry("480x260")
        self.configure(padx=12, pady=12)

        # runtime state
        self.pin = [0,0,0,0]
        self.display_mask = [True]*4
        self.pos = 0
        self.state = "EDIT"  # EDIT, LOCKED
        self.attempts = 0
        self.locked_until = 0

        # generate random target PIN
        self.target_pin = random_pin()

        self.last_action_time = time.time()
        self.inactivity_job = None
        self._press_jobs = {}   # name -> start_time
        self._repeat_job = None

        self._build_ui()
        self._start_blink()
        self._reset_inactivity_timer()

        # ensure window has focus to receive key events
        self.after(100, lambda: self.focus_set())
        self._bind_keys()

    def _build_ui(self):
        f = font.Font(size=28, weight="bold")
        self.digits_frame = tk.Frame(self)
        self.digits_frame.pack(pady=(0,10))

        self.digit_labels = []
        for i in range(4):
            lbl = tk.Label(self.digits_frame, text="0", font=f, width=2, relief="ridge", bd=3)
            lbl.grid(row=0, column=i, padx=6)
            self.digit_labels.append(lbl)

        # Info: show target PIN for testing; remove or mask in production
        self.info_label = tk.Label(self, text=f"Ziel‑PIN (Test): {''.join(map(str,self.target_pin))}", fg="gray")
        self.info_label.pack()

        btn_frame = tk.Frame(self)
        btn_frame.pack(pady=8)

        self.btn_up = tk.Button(btn_frame, text="Up", width=8)
        self.btn_up.grid(row=0, column=1)
        self.btn_left = tk.Button(btn_frame, text="Left", width=8)
        self.btn_left.grid(row=1, column=0)
        self.btn_right = tk.Button(btn_frame, text="Right", width=8)
        self.btn_right.grid(row=1, column=2)
        self.btn_down = tk.Button(btn_frame, text="Down", width=8)
        self.btn_down.grid(row=2, column=1)

        self._bind_button(self.btn_up, "UP")
        self._bind_button(self.btn_down, "DOWN")
        self._bind_button(self.btn_left, "LEFT")
        self._bind_button(self.btn_right, "RIGHT")

        self.status_label = tk.Label(self, text="", fg="red", font=font.Font(size=10))
        self.status_label.pack(pady=(6,0))

        self._update_display()

    def _bind_button(self, widget, name):
        widget.bind("<ButtonPress-1>", lambda e, n=name: self._on_press(n))
        widget.bind("<ButtonRelease-1>", lambda e, n=name: self._on_release(n))

    def _bind_keys(self):
        # Map arrow keys to the same press/release handlers
        mapping = {
            "Left": "LEFT",
            "Right": "RIGHT",
            "Up": "UP",
            "Down": "DOWN"
        }
        for key, name in mapping.items():
            self.bind(f"<KeyPress-{key}>", lambda e, n=name: self._on_key_press(n))
            self.bind(f"<KeyRelease-{key}>", lambda e, n=name: self._on_key_release(n))

    # --- Key wrappers to avoid OS autorepeat issues ---
    def _on_key_press(self, name):
        # ignore repeated KeyPress events if already pressed
        if name in self._press_jobs:
            return
        self._on_press(name)

    def _on_key_release(self, name):
        # only call release if we had a press recorded
        if name in self._press_jobs:
            self._on_release(name)

    # --- Input handling with long-press and repeat ---
    def _on_press(self, name):
        if self.state == "LOCKED":
            return
        # debounce
        self.after(DEBOUNCE_MS, lambda: self._start_press(name))

    def _start_press(self, name):
        # if already pressed (e.g., double event), ignore
        if name in self._press_jobs:
            return
        start = time.time()
        self._press_jobs[name] = start
        # schedule long-press check
        self.after(LONG_PRESS_MS, lambda: self._check_long_press(name, start))
        # schedule repeat start for Up/Down
        if name in ("UP","DOWN"):
            self.after(REPEAT_START_MS, lambda: self._start_repeat(name, start))

    def _check_long_press(self, name, start):
        if self._press_jobs.get(name) == start:
            # still pressed -> long press action
            if name == "RIGHT":
                self._submit_pin()
            elif name == "LEFT":
                if self.pos == 0:
                    self._clear_all()
                else:
                    self._set_digit(self.pos, 0)
            # Up/Down long handled by repeat

    def _start_repeat(self, name, start):
        if self._press_jobs.get(name) != start:
            return
        # perform one step and schedule next
        if name == "UP":
            self._inc_digit(self.pos)
        elif name == "DOWN":
            self._dec_digit(self.pos)
        self._repeat_job = self.after(REPEAT_INTERVAL_MS, lambda: self._start_repeat(name, start))

    def _on_release(self, name):
        start = self._press_jobs.pop(name, None)
        if start is None:
            return
        # cancel repeat if any
        if self._repeat_job:
            try:
                self.after_cancel(self._repeat_job)
            except Exception:
                pass
            self._repeat_job = None
        duration = int((time.time() - start) * 1000)
        if duration < LONG_PRESS_MS:
            # treat as short press
            self._handle_short_press(name)
        self._reset_inactivity_timer()

    def _handle_short_press(self, name):
        if name == "LEFT":
            self._move_left()
        elif name == "RIGHT":
            # If currently on 4th digit (index 3), short RIGHT triggers immediate check
            if self.pos == 3:
                self._submit_pin()
            else:
                self._move_right()
        elif name == "UP":
            self._inc_digit(self.pos)
        elif name == "DOWN":
            self._dec_digit(self.pos)

    # --- Actions ---
    def _move_left(self):
        self.pos = (self.pos - 1) % 4
        self._update_display()

    def _move_right(self):
        self.pos = (self.pos + 1) % 4
        self._update_display()

    def _inc_digit(self, idx):
        self.pin[idx] = (self.pin[idx] + 1) % 10
        self._show_temp_digit(idx)
        self._update_display()

    def _dec_digit(self, idx):
        self.pin[idx] = (self.pin[idx] - 1) % 10
        self._show_temp_digit(idx)
        self._update_display()

    def _set_digit(self, idx, val):
        self.pin[idx] = val % 10
        self._show_temp_digit(idx)
        self._update_display()

    def _clear_all(self):
        self.pin = [0,0,0,0]
        self._update_display()
        self._flash_status("Alle Ziffern gelöscht", "blue")

    def _show_temp_digit(self, idx):
        self.display_mask[idx] = False
        self._update_display()
        # cancel previous mask job if exists
        job_attr = f"_mask_job_{idx}"
        prev = getattr(self, job_attr, None)
        if prev:
            try:
                self.after_cancel(prev)
            except Exception:
                pass
        job = self.after(MASK_DELAY_MS, lambda i=idx: self._mask_digit(i))
        setattr(self, job_attr, job)

    def _mask_digit(self, idx):
        self.display_mask[idx] = True
        self._update_display()

    def _submit_pin(self):
        if self.state == "LOCKED":
            return
        self._update_display()
        if self.pin == self.target_pin:
            self._flash_status("PIN korrekt — Zugriff gewährt", "green")
            self.attempts = 0
            # generate a new random PIN for next round (optional)
            self.target_pin = random_pin()
            self.info_label.config(text=f"Ziel‑PIN (Test): {''.join(map(str,self.target_pin))}")
            self.pin = [0,0,0,0]
            self.pos = 0
            self._update_display()
        else:
            self.attempts += 1
            self._flash_status(f"Falsche PIN ({self.attempts}/{MAX_ATTEMPTS})", "red")
            if self.attempts >= MAX_ATTEMPTS:
                self._lockout()

    def _lockout(self):
        self.state = "LOCKED"
        self.locked_until = time.time() + (LOCKOUT_DURATION_MS/1000)
        self._update_display()
        self._countdown_lock()

    def _countdown_lock(self):
        remaining = int(self.locked_until - time.time())
        if remaining > 0:
            self.status_label.config(text=f"Gesperrt für {remaining}s", fg="red")
            self.after(1000, self._countdown_lock)
        else:
            self.state = "EDIT"
            self.attempts = 0
            self.status_label.config(text="")
            self._update_display()

    # --- Display / UI helpers ---
    def _update_display(self):
        for i, lbl in enumerate(self.digit_labels):
            txt = "*" if self.display_mask[i] else str(self.pin[i])
            lbl.config(text=txt)
            if i == self.pos and self.state == "EDIT":
                lbl.config(bg="#ffd", relief="solid")
            else:
                lbl.config(bg=self.cget("bg"), relief="ridge")
        if self.state == "LOCKED":
            for lbl in self.digit_labels:
                lbl.config(bg="#fdd")
        self.last_action_time = time.time()

    def _flash_status(self, text, color):
        self.status_label.config(text=text, fg=color)
        self.after(1500, lambda: self.status_label.config(text=""))

    # blinking cursor effect
    def _start_blink(self):
        self._blink_state = True
        self._do_blink()

    def _do_blink(self):
        if self.state != "EDIT":
            for lbl in self.digit_labels:
                lbl.config(font=font.Font(size=28, weight="bold"))
            self.after(500, self._do_blink)
            return
        lbl = self.digit_labels[self.pos]
        if self._blink_state:
            lbl.config(font=font.Font(size=28, weight="bold", underline=1))
        else:
            lbl.config(font=font.Font(size=28, weight="bold", underline=0))
        self._blink_state = not self._blink_state
        self.after(500, self._do_blink)

    # inactivity timeout
    def _reset_inactivity_timer(self):
        self.last_action_time = time.time()
        if self.inactivity_job:
            try:
                self.after_cancel(self.inactivity_job)
            except Exception:
                pass
        self.inactivity_job = self.after(INACTIVITY_TIMEOUT_MS, self._on_inactivity)

    def _on_inactivity(self):
        self.pin = [0,0,0,0]
        self.pos = 0
        self._update_display()
        self._flash_status("Inaktivität: Eingabe zurückgesetzt", "gray")

if __name__ == "__main__":
    app = PinSimulator()
    app.mainloop()
