import pytest
from executor.base import Executor, Intent, IntentType, ExecutorError


def test_intent_construction():
    """Intent 数据类能正确构造和序列化"""
    i = Intent(IntentType.SET_BRIGHTNESS, {"value": 50, "monitor_index": 0})
    assert i.type == IntentType.SET_BRIGHTNESS
    assert i.params == {"value": 50, "monitor_index": 0}
    assert i.to_dict() == {
        "type": "set_brightness",
        "params": {"value": 50, "monitor_index": 0},
    }


def test_executor_abc_cannot_instantiate():
    """Executor 是抽象类，不能直接实例化"""
    with pytest.raises(TypeError):
        Executor()


def test_parse_display_intent_brightness_set():
    """从意图文本解析 set_brightness"""
    from executor.base import parse_intent_from_voice_text
    intent = parse_intent_from_voice_text("亮度设为50")
    assert intent is not None
    assert intent.type == IntentType.SET_BRIGHTNESS
    assert intent.params["value"] == 50


def test_parse_display_intent_brightness_adjust():
    """从意图文本解析 adjust_brightness"""
    from executor.base import parse_intent_from_voice_text
    intent = parse_intent_from_voice_text("亮度调高10")
    assert intent is not None
    assert intent.type == IntentType.ADJUST_BRIGHTNESS
    assert intent.params["delta"] == 10


def test_parse_volume_intent():
    """从意图文本解析音量"""
    from executor.base import parse_intent_from_voice_text
    intent = parse_intent_from_voice_text("音量调到30")
    assert intent is not None
    assert intent.type == IntentType.SET_VOLUME
    assert intent.params["value"] == 30


def test_parse_app_launch_intent():
    """从意图文本解析打开应用"""
    from executor.base import parse_intent_from_voice_text
    intent = parse_intent_from_voice_text("打开微信")
    assert intent is not None
    assert intent.type == IntentType.LAUNCH_APP
    assert intent.params["name"] == "微信"


def test_parse_bilibili_intent():
    """从意图文本解析 B 站搜索"""
    from executor.base import parse_intent_from_voice_text
    intent = parse_intent_from_voice_text("B站搜索 Python 教程")
    assert intent is not None
    assert intent.type == IntentType.BILIBILI_SEARCH
    assert intent.params["keyword"] == "Python 教程"


def test_parse_local_screen_intent():
    """从意图文本解析本机屏控制"""
    from executor.base import parse_intent_from_voice_text
    intent = parse_intent_from_voice_text("本机屏幕亮一点")
    assert intent is not None
    assert intent.type == IntentType.ADJUST_LOCAL_BACKLIGHT
    assert intent.params["delta"] == 10
