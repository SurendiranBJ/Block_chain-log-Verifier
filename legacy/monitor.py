#!/usr/bin/env python3
"""
Activity Monitor for Logchain System
Captures mouse movements, clicks, and keyboard events
Writes to ~/logchain/SAMPLELOG/activity_YYYY-MM-DD.log
"""

import json
import os
import threading
import time
from datetime import datetime
from pynput import mouse, keyboard

# ── Log directory ──────────────────────────────────────────────────────────────
LOG_DIR = os.path.expanduser("~/logchain/SAMPLELOG")
os.makedirs(LOG_DIR, exist_ok=True)

_log_lock = threading.Lock()

def get_log_path():
    date_str = datetime.now().strftime("%Y-%m-%d")
    return os.path.join(LOG_DIR, f"activity_{date_str}.log")

def write_event(event: dict):
    event["timestamp"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
    line = json.dumps(event)
    log_path = get_log_path()
    with _log_lock:
        with open(log_path, "a") as f:
            f.write(line + "\n")
            f.flush()   # force write to disk immediately

# ── Mouse ──────────────────────────────────────────────────────────────────────

_last_move_time = [0.0]
MOUSE_THROTTLE_MS = 100  # log a move event every 100 ms max

def on_move(x, y):
    now = time.time()
    if (now - _last_move_time[0]) * 1000 >= MOUSE_THROTTLE_MS:
        _last_move_time[0] = now
        write_event({"type": "mouse_move", "x": x, "y": y})

def on_click(x, y, button, pressed):
    write_event({
        "type": "mouse_click",
        "x": x,
        "y": y,
        "button": str(button).replace("Button.", ""),
        "action": "pressed" if pressed else "released"
    })

def on_scroll(x, y, dx, dy):
    write_event({
        "type": "mouse_scroll",
        "x": x,
        "y": y,
        "dx": dx,
        "dy": dy
    })

# ── Keyboard ───────────────────────────────────────────────────────────────────

def _key_str(key):
    try:
        return key.char if key.char else f"[{key.name}]"
    except AttributeError:
        return f"[{str(key).replace('Key.', '')}]"

def on_press(key):
    write_event({"type": "key_press", "key": _key_str(key)})

def on_release(key):
    write_event({"type": "key_release", "key": _key_str(key)})

# ── Main ───────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    # Write a startup marker — confirms log file is created immediately
    write_event({"type": "system", "message": "Monitor started"})

    print(f"[monitor] Log directory : {LOG_DIR}")
    print(f"[monitor] Log file      : {get_log_path()}")
    print("[monitor] Press CTRL+C to stop.\n")

    mouse_listener    = mouse.Listener(on_move=on_move, on_click=on_click, on_scroll=on_scroll)
    keyboard_listener = keyboard.Listener(on_press=on_press, on_release=on_release)

    mouse_listener.start()
    keyboard_listener.start()

    try:
        mouse_listener.join()
        keyboard_listener.join()
    except KeyboardInterrupt:
        write_event({"type": "system", "message": "Monitor stopped"})
        print("\n[monitor] Stopped.")
        mouse_listener.stop()
        keyboard_listener.stop()
