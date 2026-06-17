"""共享 pytest fixtures — Plan 1 起为后续测试提供。

所有 fixture 默认 scope=function（每次测试独立），不共享可变状态。
"""
import pytest


# ── 常量 ──────────────────────────────────────────────
TEST_PC_AGENT_URL = "http://pc.test.local:18770"
TEST_PC_AGENT_TIMEOUT = 1.0
TEST_PC_AGENT_MAX_RETRIES = 1


# ── 基础 fixture ───────────────────────────────────────
@pytest.fixture
def pc_agent_url() -> str:
    """测试用 PC agent URL（不连真 PC，纯单元测试）"""
    return TEST_PC_AGENT_URL


@pytest.fixture
def dev_stub():
    """每次测试一个干净的 DevStubExecutor（call_log 清空）"""
    from executor.dev_stub import DevStubExecutor
    return DevStubExecutor()


@pytest.fixture
def pc_agent(pc_agent_url):
    """每次测试一个干净的 PCAgentExecutor，consecutive_failures=0"""
    from executor.pc_agent import PCAgentExecutor
    return PCAgentExecutor(
        base_url=pc_agent_url,
        timeout=TEST_PC_AGENT_TIMEOUT,
        max_retries=TEST_PC_AGENT_MAX_RETRIES,
    )


@pytest.fixture
def dispatcher(pc_agent, dev_stub):
    """每次测试一个干净的 ExecutorDispatcher（fail_threshold=2 便于快速触发）"""
    from executor.dispatcher import ExecutorDispatcher
    return ExecutorDispatcher(
        pc_agent=pc_agent,
        dev_stub=dev_stub,
        fail_threshold=2,  # 比默认 3 小，方便测试快速触发降级
        health_check_interval=0.5,
    )
