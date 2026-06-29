"""linux/backlight.py unit tests — mock sysfs/xrandr"""
import pytest
from unittest.mock import patch, mock_open, MagicMock


def test_get_backlight_value_reads_sysfs():
    """Read /sys/class/backlight/*/brightness current value"""
    from linux.backlight import get_backlight_value
    fake_content = "75\n"
    with patch("os.path.exists", return_value=True), \
         patch("os.listdir", return_value=["amdgpu_bl0"]), \
         patch("builtins.open", mock_open(read_data=fake_content)):
        val = get_backlight_value()
    assert val == 75


def test_set_backlight_value_writes_sysfs():
    """Write /sys/class/backlight/*/brightness 0~100"""
    from linux.backlight import set_backlight_value
    m_open = mock_open()
    with patch("os.path.exists", return_value=True), \
         patch("os.listdir", return_value=["amdgpu_bl0"]), \
         patch("builtins.open", m_open):
        set_backlight_value(50)
    handle = m_open()
    handle.write.assert_called_once_with("50\n")


def test_set_backlight_clamps_to_0_100():
    """out-of-range should be clamped"""
    from linux.backlight import set_backlight_value
    m_open = mock_open()
    with patch("os.path.exists", return_value=True), \
         patch("os.listdir", return_value=["amdgpu_bl0"]), \
         patch("builtins.open", m_open):
        set_backlight_value(150)  # should clamp to 100
        handle = m_open()
        handle.write.assert_called_once_with("100\n")
        handle.write.reset_mock()
        set_backlight_value(-10)  # should clamp to 0
        handle.write.assert_called_with("0\n")


def test_falls_back_to_xrandr_when_sysfs_missing():
    """/sys/class/backlight missing -> fallback to xrandr --brightness"""
    from linux.backlight import set_backlight_value
    with patch("os.path.exists", return_value=False), \
         patch("subprocess.run") as m_run:
        set_backlight_value(50)
    m_run.assert_called_once()
    args = m_run.call_args[0][0]
    assert "xrandr" in args
    assert "--brightness" in args
    # 50 / 100 = 0.5
    assert "0.5" in args
