"""Screen backlight control (sysfs first, xrandr fallback)"""
from __future__ import annotations
import os
import subprocess
from typing import Optional

BACKLIGHT_BASE = "/sys/class/backlight"


def _find_backlight_device() -> Optional[str]:
    """Find first backlight device name (e.g. 'amdgpu_bl0'), return None if none"""
    if not os.path.exists(BACKLIGHT_BASE):
        return None
    try:
        for name in os.listdir(BACKLIGHT_BASE):
            return name  # take first
    except OSError:
        return None
    return None


def get_backlight_value() -> int:
    """Read current backlight (0~100). Returns -1 on failure."""
    device = _find_backlight_device()
    if not device:
        return _xrandr_get_brightness()
    try:
        with open(f"{BACKLIGHT_BASE}/{device}/brightness", "r") as f:
            return int(f.read().strip())
    except Exception:
        return -1


def set_backlight_value(value: int) -> bool:
    """Set backlight (0~100, clamped). Returns whether succeeded."""
    value = max(0, min(100, int(value)))
    device = _find_backlight_device()
    if device:
        try:
            with open(f"{BACKLIGHT_BASE}/{device}/brightness", "w") as f:
                f.write(f"{value}\n")
            return True
        except (PermissionError, OSError):
            pass  # fallback to xrandr
    return _xrandr_set_brightness(value)


def _xrandr_get_brightness() -> int:
    """xrandr fallback read"""
    try:
        out = subprocess.run(
            ["xrandr", "--query", "--verbose"],
            capture_output=True, text=True, timeout=2,
        )
        for line in out.stdout.splitlines():
            if "Brightness:" in line:
                return round(float(line.split("Brightness:")[1].strip()) * 100)
    except Exception:
        pass
    return -1


def _xrandr_set_brightness(value: int) -> bool:
    """xrandr fallback write"""
    factor = value / 100
    try:
        subprocess.run(
            ["xrandr", "--output", "HDMI-1", "--brightness", str(factor)],
            capture_output=True, timeout=2,
        )
        return True
    except Exception:
        return False
