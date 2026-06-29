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
    assert result["code"] == "ERR_LOCAL_BACKLIGHT"


# ── 新增 10 个 Task 3 测试 ────────────────────────────

def test_local_set_brightness_routes_to_backlight():
    """SET_BRIGHTNESS → linux.backlight.set_backlight_value"""
    from executor.local import LocalExecutor
    from executor.base import IntentType
    exe = LocalExecutor()
    with patch("linux.backlight.set_backlight_value", return_value=True) as m_set:
        result = exe.execute_safe(Intent(IntentType.SET_BRIGHTNESS, {"value": 60, "monitor_index": 0}))
    assert result["ok"] is True
    assert result["data"]["value"] == 60
    m_set.assert_called_once_with(60)


def test_local_adjust_brightness_uses_linux_backlight():
    """ADJUST_BRIGHTNESS 走 Linux backlight"""
    from executor.local import LocalExecutor
    from executor.base import IntentType
    exe = LocalExecutor()
    with patch("linux.backlight.get_backlight_value", return_value=30), \
         patch("linux.backlight.set_backlight_value", return_value=True) as m_set:
        result = exe.execute_safe(Intent(IntentType.ADJUST_BRIGHTNESS, {"delta": 20, "monitor_index": 0}))
    assert result["ok"] is True
    assert result["data"]["value"] == 50
    m_set.assert_called_once_with(50)


def test_local_set_volume_calls_audio_io():
    """SET_VOLUME → linux.audio_io.set_volume"""
    from executor.local import LocalExecutor
    from executor.base import IntentType
    exe = LocalExecutor()
    with patch("linux.audio_io.set_volume", return_value=True) as m_set:
        result = exe.execute_safe(Intent(IntentType.SET_VOLUME, {"value": 75}))
    assert result["ok"] is True
    assert result["data"]["value"] == 75
    m_set.assert_called_once_with(75)


def test_local_adjust_volume_reads_then_writes():
    """ADJUST_VOLUME 先 get_volume 再 set"""
    from executor.local import LocalExecutor
    from executor.base import IntentType
    exe = LocalExecutor()
    with patch("linux.audio_io.get_volume", return_value=30), \
         patch("linux.audio_io.set_volume", return_value=True) as m_set:
        result = exe.execute_safe(Intent(IntentType.ADJUST_VOLUME, {"delta": 20}))
    assert result["ok"] is True
    assert result["data"]["value"] == 50
    m_set.assert_called_once_with(50)


def test_local_set_volume_returns_error_when_audio_unavailable():
    """SET_VOLUME 音频不可用返回 ERR_LOCAL_AUDIO"""
    from executor.local import LocalExecutor
    from executor.base import IntentType
    exe = LocalExecutor()
    with patch("linux.audio_io.set_volume", return_value=False):
        result = exe.execute_safe(Intent(IntentType.SET_VOLUME, {"value": 50}))
    assert result["ok"] is False
    assert result["code"] == "ERR_LOCAL_AUDIO"


def test_local_launch_app_routes_to_app_manager_linux():
    """LAUNCH_APP → app_manager_linux.launch_app"""
    from executor.local import LocalExecutor
    from executor.base import IntentType
    exe = LocalExecutor()
    with patch("app_manager_linux.launch_app",
               return_value={"ok": True, "data": {"pid": 1234, "name": "firefox"}}) as m:
        result = exe.execute_safe(Intent(IntentType.LAUNCH_APP, {"name": "firefox"}))
    assert result["ok"] is True
    assert result["data"]["pid"] == 1234
    m.assert_called_once_with("firefox")


def test_local_close_app_routes_to_app_manager_linux():
    """CLOSE_APP → app_manager_linux.close_app"""
    from executor.local import LocalExecutor
    from executor.base import IntentType
    exe = LocalExecutor()
    with patch("app_manager_linux.close_app",
               return_value={"ok": True, "data": {"term_sent": 1, "kill_sent": 0}}) as m:
        result = exe.execute_safe(Intent(IntentType.CLOSE_APP, {"name": "firefox"}))
    assert result["ok"] is True
    m.assert_called_once_with("firefox")


def test_local_focus_app_routes_to_app_manager_linux():
    """FOCUS_APP → app_manager_linux.focus_app"""
    from executor.local import LocalExecutor
    from executor.base import IntentType
    exe = LocalExecutor()
    with patch("app_manager_linux.focus_app",
               return_value={"ok": True}) as m:
        result = exe.execute_safe(Intent(IntentType.FOCUS_APP, {"name": "firefox"}))
    assert result["ok"] is True
    m.assert_called_once_with("firefox")


def test_local_list_apps_routes_to_app_manager_linux():
    """LIST_APPS → app_manager_linux.list_apps"""
    from executor.local import LocalExecutor
    from executor.base import IntentType
    exe = LocalExecutor()
    with patch("app_manager_linux.list_apps",
               return_value={"ok": True, "data": [{"name": "firefox", "pid": 1234}]}) as m:
        result = exe.execute_safe(Intent(IntentType.LIST_APPS, {}))
    assert result["ok"] is True
    assert len(result["data"]) == 1


def test_local_bilibili_search_returns_unsupported():
    """BILIBILI_SEARCH 本期不支持"""
    from executor.local import LocalExecutor
    from executor.base import IntentType
    exe = LocalExecutor()
    result = exe.execute_safe(Intent(IntentType.BILIBILI_SEARCH, {"keyword": "test"}))
    assert result["ok"] is False
    assert result["code"] == "ERR_UNSUPPORTED"


# ── I2/I3 regression tests ────────────────────────────

def test_local_set_contrast_clamps_value():
    """SET_CONTRAST value 越界被 clamp"""
    from executor.local import LocalExecutor
    from executor.base import IntentType
    exe = LocalExecutor()
    result = exe.execute_safe(Intent(IntentType.SET_CONTRAST, {"value": 999}))
    assert result["ok"] is True
    assert result["data"]["value"] == 100  # 999 → 100


def test_local_set_color_temp_clamps_value():
    """SET_COLOR_TEMP value 越界被 clamp"""
    from executor.local import LocalExecutor
    from executor.base import IntentType
    exe = LocalExecutor()
    result = exe.execute_safe(Intent(IntentType.SET_COLOR_TEMP, {"value": -50}))
    assert result["ok"] is True
    assert result["data"]["value"] == 0  # -50 → 0


def test_local_adjust_contrast_uses_delta():
    """ADJUST_CONTRAST: 50 基线 + delta"""
    from executor.local import LocalExecutor
    from executor.base import IntentType
    exe = LocalExecutor()
    result = exe.execute_safe(Intent(IntentType.ADJUST_CONTRAST, {"delta": 20}))
    assert result["ok"] is True
    assert result["data"]["value"] == 70  # 50 + 20
