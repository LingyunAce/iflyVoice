"""linux/audio_io.py unit tests — test pure functions (device listing)"""
import pytest
from unittest.mock import patch, MagicMock


def test_list_input_devices_filters_keyword():
    """List input devices containing 'usb'"""
    from linux.audio_io import list_input_devices
    fake_devices = [
        {"name": "USB Microphone", "max_input_channels": 1, "index": 0},
        {"name": "HDA Intel PCH", "max_input_channels": 2, "index": 1},
    ]
    with patch("sounddevice.query_devices", return_value=fake_devices):
        result = list_input_devices(keyword="usb")
    assert len(result) == 1
    assert "USB" in result[0]["name"]


def test_list_output_devices_filters_keyword():
    """List output devices containing 'hdmi'"""
    from linux.audio_io import list_output_devices
    fake_devices = [
        {"name": "HDMI Audio Output", "max_output_channels": 2, "index": 5},
        {"name": "Speaker", "max_output_channels": 2, "index": 6},
    ]
    with patch("sounddevice.query_devices", return_value=fake_devices):
        result = list_output_devices(keyword="hdmi")
    assert len(result) == 1
    assert "HDMI" in result[0]["name"]


def test_get_default_input_device():
    """Return default input device"""
    from linux.audio_io import get_default_input_device
    fake = {"name": "Default Mic", "index": 0, "max_input_channels": 1}
    with patch("sounddevice.query_devices", return_value=fake):
        dev = get_default_input_device()
    assert dev["name"] == "Default Mic"
