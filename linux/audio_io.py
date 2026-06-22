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


def set_volume(percent: int) -> bool:
    """Set system volume (0-100). Returns True on success.

    Uses pulsectl. Returns False on any error.
    """
    try:
        import pulsectl
        percent = max(0, min(100, int(percent)))
        with pulsectl.Pulse("iflyvoice") as pulse:
            for sink in pulse.sink_list():
                sink.volume = pulsectl.PulseVolumeInfo("100%").with_factor(percent / 100.0)
                pulse.sink_volume_set(sink, sink.volume)
        return True
    except Exception:
        return False


def get_volume() -> int:
    """Get current system volume (0-100). Returns -1 on error.

    Reads the first available sink. If multiple sinks exist, returns
    the average across them rounded to int.
    """
    try:
        import pulsectl
        with pulsectl.Pulse("iflyvoice") as pulse:
            sinks = pulse.sink_list()
            if not sinks:
                return -1
            # sinks[*].volume.value is a list (one per channel); average
            avg = sum(s.volume.value) / len(s.volume.value)
            return max(0, min(100, round(avg * 100)))
    except Exception:
        return -1
