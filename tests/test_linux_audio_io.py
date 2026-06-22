"""linux/audio_io.py unit tests — test pure functions (device listing)"""
import sys
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


@pytest.mark.skipif(sys.platform == "win32", reason="pulsectl requires Linux (libpulse.so.0)")
def test_set_volume_uses_pulsectl():
    """set_volume(60) 调 PulseAudio 把音量设到 60%"""
    from linux import audio_io
    mock_sink = MagicMock()
    mock_sink.volume = MagicMock()
    mock_pulse_instance = MagicMock()
    mock_pulse_instance.__enter__ = MagicMock(return_value=mock_pulse_instance)
    mock_pulse_instance.__exit__ = MagicMock(return_value=False)
    mock_pulse_instance.sink_list = MagicMock(return_value=[mock_sink])
    with patch.object(audio_io, "Pulse", create=True, return_value=mock_pulse_instance), \
         patch.object(audio_io, "PulseVolumeInfo", create=True) as mock_pvi:
        mock_pvi.return_value.with_factor = MagicMock(return_value=MagicMock())
        result = audio_io.set_volume(60)
    assert result is True
    mock_pulse_instance.sink_volume_set.assert_called()


@pytest.mark.skipif(sys.platform == "win32", reason="pulsectl requires Linux (libpulse.so.0)")
def test_get_volume_returns_percent():
    """get_volume() 返回 0-100 的整数百分比"""
    from linux import audio_io
    mock_sink = MagicMock()
    mock_sink.volume.value = [0.42, 0.42]  # 双声道 42%
    mock_pulse_instance = MagicMock()
    mock_pulse_instance.__enter__ = MagicMock(return_value=mock_pulse_instance)
    mock_pulse_instance.__exit__ = MagicMock(return_value=False)
    mock_pulse_instance.sink_list = MagicMock(return_value=[mock_sink])
    with patch.object(audio_io, "Pulse", create=True, return_value=mock_pulse_instance):
        result = audio_io.get_volume()
    assert result == 42


@pytest.mark.skipif(sys.platform == "win32", reason="pulsectl requires Linux (libpulse.so.0)")
def test_set_volume_clamps_to_0_100():
    """set_volume 越界值被夹到 0-100"""
    from linux import audio_io
    captured_factor = []
    mock_sink = MagicMock()
    mock_pulse_instance = MagicMock()
    mock_pulse_instance.__enter__ = MagicMock(return_value=mock_pulse_instance)
    mock_pulse_instance.__exit__ = MagicMock(return_value=False)
    mock_pulse_instance.sink_list = MagicMock(return_value=[mock_sink])

    def fake_with_factor(f):
        captured_factor.append(f)
        return MagicMock()
    with patch.object(audio_io, "Pulse", create=True, return_value=mock_pulse_instance), \
         patch.object(audio_io, "PulseVolumeInfo", create=True) as mock_pvi:
        mock_pvi.return_value.with_factor = fake_with_factor
        result = audio_io.set_volume(150)
    assert result is True
    # 150% 应被夹到 100%，对应 factor=1.0
    assert all(0.0 <= f <= 1.0 for f in captured_factor)
    assert any(abs(f - 1.0) < 1e-9 for f in captured_factor)
