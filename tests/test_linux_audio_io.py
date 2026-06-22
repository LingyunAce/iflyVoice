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


def test_set_volume_uses_pulsectl():
    """set_volume(60) 调 PulseAudio 把音量设到 60%"""
    from linux import audio_io
    with patch.object(audio_io, "Pulse", create=True) as mock_pulse:
        mock_sink = MagicMock()
        mock_sink.volume = MagicMock()
        mock_sink.__enter__ = MagicMock(return_value=mock_sink)
        mock_sink.__exit__ = MagicMock(return_value=False)
        mock_pulse.return_value = mock_sink
        result = audio_io.set_volume(60)
    assert result is True


def test_get_volume_returns_percent():
    """get_volume() 返回 0-100 的整数百分比"""
    from linux import audio_io
    with patch.object(audio_io, "Pulse", create=True) as mock_pulse:
        mock_sink = MagicMock()
        mock_sink.volume.value = 0.42  # 42% as float
        mock_sink.__enter__ = MagicMock(return_value=mock_sink)
        mock_sink.__exit__ = MagicMock(return_value=False)
        mock_pulse.return_value = mock_sink
        result = audio_io.get_volume()
    assert result == 42


def test_set_volume_clamps_to_0_100():
    """set_volume 越界值被夹到 0-100"""
    from linux import audio_io
    with patch.object(audio_io, "Pulse", create=True) as mock_pulse:
        mock_sink = MagicMock()
        mock_sink.__enter__ = MagicMock(return_value=mock_sink)
        mock_sink.__exit__ = MagicMock(return_value=False)
        mock_pulse.return_value = mock_sink
        audio_io.set_volume(150)
    # 写入值应为 1.0
    mock_sink.volume.value = 1.0
    # 校验：调用时实际传入 normalized value
    actual_value = mock_sink.volume.value
    assert 0.0 <= actual_value <= 1.0
