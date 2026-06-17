"""linux/display.py unit tests — xrandr parsing"""
import pytest
from unittest.mock import patch, MagicMock


SAMPLE_XRANDR = """\
Screen 0: minimum 320 x 200, current 1920 x 1080, maximum 16384 x 16384
HDMI-1 connected 1920x1080+0+0 (normal left inverted right x axis y axis) 600mm x 340mm
   1920x1080     60.00*+  50.00
DP-1 disconnected (normal left inverted right x axis y axis)
"""


def test_list_connected_outputs():
    """List all connected outputs"""
    from linux.display import list_connected_outputs
    with patch("subprocess.run") as m_run:
        m_run.return_value = MagicMock(stdout=SAMPLE_XRANDR, returncode=0)
        outputs = list_connected_outputs()
    assert "HDMI-1" in outputs
    assert "DP-1" not in outputs  # disconnected


def test_get_current_resolution():
    """Get current display resolution"""
    from linux.display import get_current_resolution
    with patch("subprocess.run") as m_run:
        m_run.return_value = MagicMock(stdout=SAMPLE_XRANDR, returncode=0)
        res = get_current_resolution("HDMI-1")
    assert res == (1920, 1080)
