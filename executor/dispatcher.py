"""Executor 调度器 — 决定每个意图走 pc_agent 还是 dev_stub
支持 PC 失败降级：连续 N 次失败后，所有 PC 意图降级到 stub（仅 dev 用）
"""
from __future__ import annotations
import threading
import time
from typing import Optional
from executor.base import Executor, Intent, IntentType
from executor.dev_stub import DevStubExecutor
from executor.pc_agent import PCAgentExecutor


# 走 PC agent 的意图（PC 侧功能）
_PC_INTENTS = {
    IntentType.SET_BRIGHTNESS, IntentType.ADJUST_BRIGHTNESS,
    IntentType.SET_CONTRAST, IntentType.ADJUST_CONTRAST,
    IntentType.SET_COLOR_TEMP,
    IntentType.SET_INPUT, IntentType.LIST_INPUTS,
    IntentType.SET_VOLUME, IntentType.ADJUST_VOLUME,
    IntentType.LAUNCH_APP, IntentType.CLOSE_APP, IntentType.FOCUS_APP, IntentType.LIST_APPS,
    IntentType.BILIBILI_SEARCH,
}

# 走本地（stub，本期 Plan 2 替换为真实实现）
_LOCAL_INTENTS = {
    IntentType.SET_LOCAL_BACKLIGHT, IntentType.ADJUST_LOCAL_BACKLIGHT,
}


class ExecutorDispatcher:
    """意图→执行器 调度器

    使用方式：
        disp = ExecutorDispatcher(pc_agent=PCAgentExecutor(...), dev_stub=DevStubExecutor())
        result = disp.dispatch(intent)
    """

    def __init__(self, pc_agent: PCAgentExecutor, dev_stub: DevStubExecutor,
                 fail_threshold: int = 3, health_check_interval: float = 30.0):
        self.pc_agent = pc_agent
        self.dev_stub = dev_stub
        self.fail_threshold = fail_threshold
        self.health_check_interval = health_check_interval
        self._last_health_check: float = 0.0
        self._health_check_ok: bool = False
        self._health_lock = threading.Lock()

    def dispatch(self, intent: Intent) -> dict:
        """派发意图到对应执行器"""
        exe = self._route(intent)
        return exe.execute_safe(intent)

    def _route(self, intent_type: IntentType) -> Executor:
        """根据意图类型 + PC 健康状态选择执行器"""
        if intent_type in _LOCAL_INTENTS:
            return self.dev_stub  # 本期 stub；Plan 2 替换为 LocalExecutor

        # PC 意图：检查 PC 是否健康
        if self._is_pc_healthy():
            return self.pc_agent
        else:
            return self.dev_stub  # 降级

    def _is_pc_healthy(self) -> bool:
        """PC 健康判定：连续失败 < 阈值 才算健康；否则按间隔心跳探测一次

        缓存策略：探测成功后缓存为 True，后续直接走 PC；
        探测失败后缓存为 False，到下一探测窗口才再探测。
        """
        if self.pc_agent.consecutive_failures < self.fail_threshold:
            return True

        # 超过阈值：限速心跳探测（加锁防 TOCTOU 并发踩状态）
        with self._health_lock:
            now = time.time()

            # 探测成功过 → 直接信任（已恢复）
            if self._health_check_ok:
                return True

            # 探测失败过 → 限速，到时间才再探测
            if now - self._last_health_check < self.health_check_interval:
                return False

            # 探测
            self._last_health_check = now
            self._health_check_ok = self.pc_agent.health_check()
            if self._health_check_ok:
                # 健康了，清零失败计数
                self.pc_agent._record_success()  # TODO: replace with reset_failures() in B.3
            return self._health_check_ok
