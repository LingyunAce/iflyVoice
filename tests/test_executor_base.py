import pytest
from executor.base import Executor, Intent, IntentType, ExecutorError
from executor.dev_stub import DevStubExecutor


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


def test_dev_stub_set_brightness():
    """dev_stub 能处理 set_brightness"""
    exe = DevStubExecutor()
    result = exe.execute_safe(Intent(IntentType.SET_BRIGHTNESS, {"value": 50, "monitor_index": 0}))
    assert result["ok"] is True
    assert result["data"]["actual"] == 50
    assert "fake" in result["data"]["note"]


def test_dev_stub_launch_app():
    """dev_stub 能处理 launch_app"""
    exe = DevStubExecutor()
    result = exe.execute_safe(Intent(IntentType.LAUNCH_APP, {"name": "微信"}))
    assert result["ok"] is True
    assert result["data"]["name"] == "微信"


def test_dev_stub_local_backlight_records_state():
    """dev_stub 维护本机屏状态的内部字典"""
    exe = DevStubExecutor()
    exe.execute_safe(Intent(IntentType.ADJUST_LOCAL_BACKLIGHT, {"delta": 10}))
    exe.execute_safe(Intent(IntentType.ADJUST_LOCAL_BACKLIGHT, {"delta": 20}))
    state = exe.get_local_state()
    assert state["backlight"] == 30


def test_dev_stub_call_log_is_capped():
    """call_log 应该限容，防止内存无限增长"""
    exe = DevStubExecutor()
    # 发出 1500 次调用（超过上限 1000）
    for i in range(1500):
        exe.execute_safe(Intent(IntentType.LAUNCH_APP, {"name": f"app{i}"}))
    log = exe.get_call_log()
    # 应该只保留最后 1000 条
    assert len(log) == 1000
    # 第一条应该是 app500（1500-1000）
    assert log[0]["params"]["name"] == "app500"
    # 最后一条应该是 app1499
    assert log[-1]["params"]["name"] == "app1499"


def test_dev_stub_clear_call_log():
    """clear_call_log() 应该清空 log"""
    exe = DevStubExecutor()
    exe.execute_safe(Intent(IntentType.LAUNCH_APP, {"name": "wechat"}))
    exe.execute_safe(Intent(IntentType.LAUNCH_APP, {"name": "qq"}))
    assert len(exe.get_call_log()) == 2
    exe.clear_call_log()
    assert len(exe.get_call_log()) == 0


# Tests for the conftest.py shared fixtures


def test_conftest_pc_agent_url_fixture(pc_agent_url):
    """pc_agent_url fixture 返回标准测试 URL"""
    assert pc_agent_url == "http://pc.test.local:18770"
    assert pc_agent_url.startswith("http://")


def test_conftest_dev_stub_fixture(dev_stub):
    """dev_stub fixture 返回干净的 DevStubExecutor"""
    from executor.dev_stub import DevStubExecutor
    assert isinstance(dev_stub, DevStubExecutor)
    # 每次都返回新的（不共享状态）
    assert dev_stub.get_call_log() == []


def test_conftest_pc_agent_fixture(pc_agent):
    """pc_agent fixture 返回 PCAgentExecutor 指向测试 URL"""
    from executor.pc_agent import PCAgentExecutor
    assert isinstance(pc_agent, PCAgentExecutor)
    assert pc_agent.base_url == "http://pc.test.local:18770"
    assert pc_agent.consecutive_failures == 0


def test_conftest_dispatcher_fixture(dispatcher):
    """dispatcher fixture 返回 ExecutorDispatcher（Phase 1: PC 路由到 local）"""
    from executor.dispatcher import ExecutorDispatcher
    from executor.local import LocalExecutor
    assert isinstance(dispatcher, ExecutorDispatcher)
    # Phase 1: SET_BRIGHTNESS 走 local，不走 pc_agent
    from executor.base import IntentType
    assert dispatcher._route(IntentType.SET_BRIGHTNESS) is dispatcher.local_executor
    assert isinstance(dispatcher.local_executor, LocalExecutor)
