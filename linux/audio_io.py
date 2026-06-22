"""Audio input/output (sounddevice wrapper, USB/HDA/HDMI device filtering) + system volume (pulsectl, Linux only)"""
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
    Compatible with pulsectl 24+ (volume_set_all_chans) and older (PulseVolumeInfo).
    """
    try:
        import pulsectl
        percent = max(0, min(100, int(percent)))
        factor = percent / 100.0
        with pulsectl.Pulse("iflyvoice") as pulse:
            for sink in pulse.sink_list():
                pulse.volume_set_all_chans(sink, factor)
        return True
    except Exception:
        return False


def _sink_channels(sink) -> list:
    """Extract per-channel volume values from a sink.

    Compatible with pulsectl 24+ (.values) and older versions (.value).
    """
    vol = sink.volume
    if hasattr(vol, "values"):           # pulsectl >= 24
        return list(vol.values)
    return list(vol.value)               # pulsectl < 24


def get_volume() -> int:
    """Get current system volume (0-100). Returns -1 on error.

    Reads the volume of the first available PulseAudio sink.
    Each channel of the sink is averaged and rounded to int.
    """
    try:
        import pulsectl
        with pulsectl.Pulse("iflyvoice") as pulse:
            sinks = pulse.sink_list()
            if not sinks:
                return -1
            first_sink = sinks[0]
            channels = _sink_channels(first_sink)
            if not channels:
                return -1
            avg = sum(channels) / len(channels)
            return max(0, min(100, round(avg * 100)))
    except Exception:
        return -1
