import pytest
import responses
from executor.pc_agent import PCAgentExecutor
from executor.base import Intent, IntentType, ExecutorError


@pytest.fixture
def pc():
    return PCAgentExecutor(base_url="http://pc.local:18770", timeout=1.0, max_retries=2)


@responses.activate
def test_set_brightness_success(pc):
    """set_brightness 成功路径"""
    responses.add(
        responses.POST,
        "http://pc.local:18770/display/brightness",
        json={"ok": True, "data": {"actual": 50}},
        status=200,
    )
    result = pc.execute_safe(Intent(IntentType.SET_BRIGHTNESS, {"value": 50, "monitor_index": 0}))
    assert result["ok"] is True
    assert result["data"]["actual"] == 50
    assert len(responses.calls) == 1


@responses.activate
def test_set_brightness_retries_on_5xx(pc):
    """5xx 触发重试，最终失败返回标准错误"""
    responses.add(
        responses.POST,
        "http://pc.local:18770/display/brightness",
        json={"ok": False, "err": "boom"},
        status=500,
    )
    responses.add(
        responses.POST,
        "http://pc.local:18770/display/brightness",
        json={"ok": False, "err": "boom"},
        status=500,
    )
    responses.add(
        responses.POST,
        "http://pc.local:18770/display/brightness",
        json={"ok": False, "err": "boom"},
        status=500,
    )
    result = pc.execute_safe(Intent(IntentType.SET_BRIGHTNESS, {"value": 50, "monitor_index": 0}))
    assert result["ok"] is False
    assert result["code"] == "ERR_INTERNAL"
    assert len(responses.calls) == 3  # max_retries=2 → 3 次总尝试


@responses.activate
def test_set_brightness_recovers_on_retry(pc):
    """第一次 5xx，第二次成功"""
    responses.add(
        responses.POST,
        "http://pc.local:18770/display/brightness",
        json={"ok": False, "err": "transient"},
        status=503,
    )
    responses.add(
        responses.POST,
        "http://pc.local:18770/display/brightness",
        json={"ok": True, "data": {"actual": 60}},
        status=200,
    )
    result = pc.execute_safe(Intent(IntentType.SET_BRIGHTNESS, {"value": 60, "monitor_index": 0}))
    assert result["ok"] is True
    assert result["data"]["actual"] == 60
    assert len(responses.calls) == 2


@responses.activate
def test_set_brightness_timeout_treated_as_failure(pc):
    """连接超时算失败，进入重试"""
    import requests as real_requests
    responses.add(
        responses.POST,
        "http://pc.local:18770/display/brightness",
        body=real_requests.exceptions.Timeout(),
    )
    responses.add(
        responses.POST,
        "http://pc.local:18770/display/brightness",
        body=real_requests.exceptions.Timeout(),
    )
    responses.add(
        responses.POST,
        "http://pc.local:18770/display/brightness",
        body=real_requests.exceptions.Timeout(),
    )
    result = pc.execute_safe(Intent(IntentType.SET_BRIGHTNESS, {"value": 50, "monitor_index": 0}))
    assert result["ok"] is False
    assert "PC" in result["err"] or "timeout" in result["err"].lower()


@responses.activate
def test_launch_app_pc_returns_4xx(pc):
    """PC 端业务错误（4xx）不重试，直接透传"""
    responses.add(
        responses.POST,
        "http://pc.local:18770/apps/launch",
        json={"ok": False, "err": "找不到应用", "code": "ERR_APP_NOT_FOUND"},
        status=404,
    )
    result = pc.execute_safe(Intent(IntentType.LAUNCH_APP, {"name": "不存在的app"}))
    assert result["ok"] is False
    assert result["code"] == "ERR_APP_NOT_FOUND"
    assert len(responses.calls) == 1  # 4xx 不重试


@responses.activate
def test_health_check(pc):
    """健康检查返回 True/False"""
    responses.add(responses.GET, "http://pc.local:18770/health", json={"ok": True, "version": "0.1"}, status=200)
    assert pc.health_check() is True

    responses.reset()
    responses.add(responses.GET, "http://pc.local:18770/health", json={"ok": False}, status=500)
    assert pc.health_check() is False


def test_reset_failures_clears_counter():
    """reset_failures() 应清零 _consecutive_failures"""
    from executor.pc_agent import PCAgentExecutor
    pc = PCAgentExecutor(base_url="http://pc.local:18770")
    pc._record_failure()
    pc._record_failure()
    pc._record_failure()
    assert pc.consecutive_failures == 3
    pc.reset_failures()
    assert pc.consecutive_failures == 0


def test_reset_failures_is_public():
    """reset_failures 应是公开方法（无下划线前缀）"""
    from executor.pc_agent import PCAgentExecutor
    assert hasattr(PCAgentExecutor, "reset_failures"), "PCAgentExecutor 缺公开方法 reset_failures()"
    assert callable(PCAgentExecutor.reset_failures)


@responses.activate
def test_invalid_json_on_2xx_returns_internal_error(pc):
    """2xx 响应含 invalid JSON 时，返回 ERR_INTERNAL（不是崩）"""
    responses.add(
        responses.POST,
        "http://pc.local:18770/display/brightness",
        body="not valid json {",
        status=200,
    )
    result = pc.execute_safe(Intent(IntentType.SET_BRIGHTNESS, {"value": 50, "monitor_index": 0}))
    assert result["ok"] is False
    assert result["code"] == "ERR_INTERNAL"
    assert "json" in result["err"].lower() or "invalid" in result["err"].lower()


@responses.activate
def test_invalid_json_on_4xx_returns_internal_error(pc):
    """4xx 响应含 invalid JSON 时，返回 ERR_INTERNAL"""
    responses.add(
        responses.POST,
        "http://pc.local:18770/display/brightness",
        body="not valid json {",
        status=404,
    )
    result = pc.execute_safe(Intent(IntentType.SET_BRIGHTNESS, {"value": 50, "monitor_index": 0}))
    assert result["ok"] is False
    assert result["code"] == "ERR_INTERNAL"
