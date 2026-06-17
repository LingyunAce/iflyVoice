"""Audio input/output — sounddevice wrapper, supports USB/HDA/HDMI device filtering"""
from __future__ import annotations
from typing import Optional
import sounddevice as sd


def list_input_devices(keyword: Optional[str] = None) -> list[dict]:
    """List input devices (max_input_channels > 0). Optional keyword filter."""
    devices = sd.query_devices()
    result = []
    for idx, dev in enumerate(devices):
        if dev.get("max_input_channels", 0) <= 0:
            continue
        item = {"index": idx, **dev}
        if keyword is None or keyword.lower() in dev["name"].lower():
            result.append(item)
    return result


def list_output_devices(keyword: Optional[str] = None) -> list[dict]:
    """List output devices"""
    devices = sd.query_devices()
    result = []
    for idx, dev in enumerate(devices):
        if dev.get("max_output_channels", 0) <= 0:
            continue
        item = {"index": idx, **dev}
        if keyword is None or keyword.lower() in dev["name"].lower():
            result.append(item)
    return result


def get_default_input_device() -> Optional[dict]:
    """Default input device"""
    try:
        idx = sd.default.device[0]
        if idx < 0:
            return None
        dev = sd.query_devices(idx)
        return {"index": idx, **dev}
    except Exception:
        return None


def get_default_output_device() -> Optional[dict]:
    """Default output device"""
    try:
        idx = sd.default.device[1]
        if idx < 0:
            return None
        dev = sd.query_devices(idx)
        return {"index": idx, **dev}
    except Exception:
        return None
