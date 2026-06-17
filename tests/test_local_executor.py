from unittest.mock import patch
from executor.local import LocalExecutor
from executor.base import Intent, IntentType


def test_local_set_backlight_calls_linux_module():
    """SET_LOCAL_BACKLIGHT calls linux.backlight.set_backlight_value"""
    exe = LocalExecutor()
    with patch("linux.backlight.set_backlight_value", return_value=True) as m:
        result = exe.execute_safe(Intent(IntentType.SET_LOCAL_BACKLIGHT, {"value": 60}))
    assert result["ok"] is True
    assert result["data"]["value"] == 60
    m.assert_called_once_with(60)


def test_local_adjust_backlight_reads_then_writes():
    """ADJUST_LOCAL_BACKLIGHT reads current value then adjusts"""
    exe = LocalExecutor()
    with patch("linux.backlight.get_backlight_value", return_value=30) as m_get, \
         patch("linux.backlight.set_backlight_value", return_value=True) as m_set:
        result = exe.execute_safe(Intent(IntentType.ADJUST_LOCAL_BACKLIGHT, {"delta": 20}))
    assert result["ok"] is True
    assert result["data"]["value"] == 50  # 30 + 20
    m_get.assert_called_once()
    m_set.assert_called_once_with(50)


def test_local_returns_error_when_backlight_unavailable():
    """Returns error when backlight unavailable"""
    exe = LocalExecutor()
    with patch("linux.backlight.set_backlight_value", return_value=False):
        result = exe.execute_safe(Intent(IntentType.SET_LOCAL_BACKLIGHT, {"value": 60}))
    assert result["ok"] is False
    assert result["code"] == "ERR_BACKLIGHT_UNAVAILABLE"
