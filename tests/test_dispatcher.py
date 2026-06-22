import threading

import pytest
from executor.dispatcher import ExecutorDispatcher
from executor.base import Intent, IntentType
from executor.dev_stub import DevStubExecutor
from executor.pc_agent import PCAgentExecutor


def test_dispatcher_routes_pc_intent_to_local_after_phase1():
    """Phase 1: 显示器/音量/应用/B 站 全部走 local（PC 路径已禁用）"""
    from executor.local import LocalExecutor
    pc = PCAgentExecutor("http://pc.local:18770")
    stub = DevStubExecutor()
    disp = ExecutorDispatcher(pc_agent=pc, dev_stub=stub)

    target = disp._route(IntentType.SET_BRIGHTNESS)
    assert isinstance(target, LocalExecutor)

    target = disp._route(IntentType.LAUNCH_APP)
    assert isinstance(target, LocalExecutor)

    target = disp._route(IntentType.BILIBILI_SEARCH)
    assert isinstance(target, LocalExecutor)


def test_dispatcher_routes_local_intent_to_local_executor():
    """LOCAL intent routes to LocalExecutor"""
    from executor.local import LocalExecutor
    stub = DevStubExecutor()
    pc = PCAgentExecutor("http://pc.local:18770")
    local = LocalExecutor()
    disp = ExecutorDispatcher(pc_agent=pc, dev_stub=stub, local_executor=local)

    target = disp._route(IntentType.ADJUST_LOCAL_BACKLIGHT)
    assert isinstance(target, LocalExecutor)


def test_dispatcher_routes_local_to_local_executor(dispatcher, dev_stub):
    """LOCAL intent routes to LocalExecutor, not dev_stub"""
    from executor.local import LocalExecutor
    target = dispatcher._route(IntentType.ADJUST_LOCAL_BACKLIGHT)
    assert isinstance(target, LocalExecutor)
    assert target is not dev_stub


def test_dispatcher_phase1_ignores_pc_health_state():
    """Phase 1: 即使 PC 失败 N 次，所有 intent 仍走 local（不降级到 stub）"""
    from executor.local import LocalExecutor
    stub = DevStubExecutor()
    pc = PCAgentExecutor("http://pc.local:18770")
    disp = ExecutorDispatcher(pc_agent=pc, dev_stub=stub, fail_threshold=3)

    # 模拟 PC 失败（Phase 1 下应被忽略）
    pc._record_failure()
    pc._record_failure()
    pc._record_failure()

    # 仍走 local，不走 stub
    target = disp._route(IntentType.SET_BRIGHTNESS)
    assert isinstance(target, LocalExecutor)
    assert target is not stub


def test_dispatcher_health_check_state_preserved_for_future_pc():
    """健康检查状态保留（未来启用 PC agent 时还用）"""
    stub = DevStubExecutor()
    pc = PCAgentExecutor("http://pc.local:18770")
    disp = ExecutorDispatcher(pc_agent=pc, dev_stub=stub, fail_threshold=2, health_check_interval=0)

    pc._record_failure()
    pc._record_failure()

    # 健康检查状态字段保留供未来使用
    disp._last_health_check = 0
    disp._health_check_ok = True

    # _is_pc_healthy 仍可调用
    assert disp._is_pc_healthy() is True


def test_dispatcher_concurrent_routes_safe():
    """并发调用 _route 不应崩溃或死锁"""
    from executor.dispatcher import ExecutorDispatcher
    from executor.dev_stub import DevStubExecutor
    from executor.pc_agent import PCAgentExecutor
    from executor.base import Intent, IntentType

    pc = PCAgentExecutor("http://pc.local:18770")
    stub = DevStubExecutor()
    disp = ExecutorDispatcher(pc_agent=pc, dev_stub=stub)

    # 让 PC "失败" 3 次，触发 circuit breaker
    pc._record_failure()
    pc._record_failure()
    pc._record_failure()

    errors = []

    def worker():
        try:
            for _ in range(50):
                disp._route(IntentType.SET_BRIGHTNESS)
        except Exception as e:
            errors.append(e)

    threads = [threading.Thread(target=worker) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=5)

    assert not errors, f"并发调用出错: {errors}"


# ── OpenClaw Phase 1: 所有 intent 走 local ───────────────────

def test_set_brightness_routes_to_local_not_pc():
    """SET_BRIGHTNESS 走 LocalExecutor（不再走 PC agent）"""
    from executor.base import Intent, IntentType
    from unittest.mock import MagicMock
    pc_agent = MagicMock()
    local = MagicMock()
    local.execute_safe.return_value = {"ok": True, "data": {"value": 50}}
    from executor.dispatcher import ExecutorDispatcher
    disp = ExecutorDispatcher(pc_agent=pc_agent, dev_stub=MagicMock(),
                              local_executor=local, fail_threshold=1)
    disp.dispatch(Intent(IntentType.SET_BRIGHTNESS, {"value": 50}))
    local.execute_safe.assert_called_once()
    pc_agent.execute_safe.assert_not_called()


def test_pc_agent_none_falls_back_to_local():
    """pc_agent=None 时所有 intent 都走 local"""
    from executor.base import Intent, IntentType
    from unittest.mock import MagicMock
    local = MagicMock()
    local.execute_safe.return_value = {"ok": True}
    from executor.dispatcher import ExecutorDispatcher
    disp = ExecutorDispatcher(pc_agent=None, dev_stub=MagicMock(),
                              local_executor=local, fail_threshold=1)
    disp.dispatch(Intent(IntentType.SET_VOLUME, {"value": 30}))
    local.execute_safe.assert_called_once()


def test_launch_app_routes_to_local():
    """LAUNCH_APP 走 LocalExecutor"""
    from executor.base import Intent, IntentType
    from unittest.mock import MagicMock
    pc_agent = MagicMock()
    local = MagicMock()
    local.execute_safe.return_value = {"ok": True, "data": {"pid": 1234}}
    from executor.dispatcher import ExecutorDispatcher
    disp = ExecutorDispatcher(pc_agent=pc_agent, dev_stub=MagicMock(),
                              local_executor=local, fail_threshold=1)
    disp.dispatch(Intent(IntentType.LAUNCH_APP, {"name": "firefox"}))
    local.execute_safe.assert_called_once()
    pc_agent.execute_safe.assert_not_called()
