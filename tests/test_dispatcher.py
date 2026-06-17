import threading

import pytest
from executor.dispatcher import ExecutorDispatcher
from executor.base import Intent, IntentType
from executor.dev_stub import DevStubExecutor
from executor.pc_agent import PCAgentExecutor


def test_dispatcher_routes_pc_intent_to_pc_agent():
    """显示器/音量/应用/B 站 走 pc_agent"""
    pc = PCAgentExecutor("http://pc.local:18770")
    stub = DevStubExecutor()
    disp = ExecutorDispatcher(pc_agent=pc, dev_stub=stub)

    target = disp._route(IntentType.SET_BRIGHTNESS)
    assert target is pc

    target = disp._route(IntentType.LAUNCH_APP)
    assert target is pc

    target = disp._route(IntentType.BILIBILI_SEARCH)
    assert target is pc


def test_dispatcher_routes_local_intent_to_stub():
    """本机屏意图走 stub（本期 dev_stub，本机实现在 Plan 2）"""
    stub = DevStubExecutor()
    pc = PCAgentExecutor("http://pc.local:18770")
    disp = ExecutorDispatcher(pc_agent=pc, dev_stub=stub)

    target = disp._route(IntentType.ADJUST_LOCAL_BACKLIGHT)
    assert target is stub


def test_dispatcher_falls_back_to_stub_when_pc_unhealthy():
    """PC 连续失败 N 次后，所有意图走 stub（降级）"""
    stub = DevStubExecutor()
    pc = PCAgentExecutor("http://pc.local:18770")
    disp = ExecutorDispatcher(pc_agent=pc, dev_stub=stub, fail_threshold=3)

    # 模拟 PC 失败
    pc._record_failure()
    pc._record_failure()
    pc._record_failure()

    # PC 意图也走 stub
    target = disp._route(IntentType.SET_BRIGHTNESS)
    assert target is stub


def test_dispatcher_recovers_after_pc_health_check():
    """健康检查通过后恢复走 PC"""
    stub = DevStubExecutor()
    pc = PCAgentExecutor("http://pc.local:18770")
    disp = ExecutorDispatcher(pc_agent=pc, dev_stub=stub, fail_threshold=2, health_check_interval=0)

    pc._record_failure()
    pc._record_failure()

    # 模拟健康检查成功
    disp._last_health_check = 0
    disp._health_check_ok = True

    target = disp._route(IntentType.SET_BRIGHTNESS)
    assert target is pc


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
