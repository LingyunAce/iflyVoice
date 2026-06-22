"""Executor 调度器 — 决定每个意图走哪个执行器。
Phase 1 (OpenClaw 集成): 全部走 LocalExecutor；PC agent 类保留供未来使用。
支持 PC 失败降级：连续 N 次失败后，所有 PC 意图降级到 stub（仅 dev 用，PC 重新启用时生效）。
"""
from __future__ import annotations
import threading
import time
from typing import Optional
from executor.base import Executor, Intent, IntentType
from executor.dev_stub import DevStubExecutor
from executor.local import LocalExecutor
from executor.pc_agent import PCAgentExecutor


# 走本地（板子端）执行所有 intent — OpenClaw 集成 Phase 1
# PC 端能力（亮度/音量/应用）也由板子本地实现，不走 Win PC
_LOCAL_INTENTS = {
    # 本机（legacy）
    IntentType.SET_LOCAL_BACKLIGHT, IntentType.ADJUST_LOCAL_BACKLIGHT,
    # 显示器（Plan 1 走 PC；Phase 1 改走板子 sysfs/xrandr）
    IntentType.SET_BRIGHTNESS, IntentType.ADJUST_BRIGHTNESS,
    IntentType.SET_CONTRAST, IntentType.ADJUST_CONTRAST,
    IntentType.SET_COLOR_TEMP,
    IntentType.SET_INPUT, IntentType.LIST_INPUTS,
    # 音量
    IntentType.SET_VOLUME, IntentType.ADJUST_VOLUME,
    # 应用
    IntentType.LAUNCH_APP, IntentType.CLOSE_APP,
    IntentType.FOCUS_APP, IntentType.LIST_APPS,
    # B 站（本期不支持，由 LocalExecutor 返回 ERR_UNSUPPORTED）
    IntentType.BILIBILI_SEARCH,
}

# PC agent 路径暂留空 — 未来要连 Win PC 时再启用
_PC_INTENTS: set = set()


class ExecutorDispatcher:
    """意图→执行器 调度器

    使用方式：
        disp = ExecutorDispatcher(pc_agent=PCAgentExecutor(...), dev_stub=DevStubExecutor())
        result = disp.dispatch(intent)
    """

    def __init__(self, pc_agent: Optional[PCAgentExecutor] = None,
                 dev_stub: Optional[DevStubExecutor] = None,
                 local_executor: Optional[LocalExecutor] = None,
                 fail_threshold: int = 3, health_check_interval: float = 30.0):
        self.pc_agent = pc_agent
        self.dev_stub = dev_stub or DevStubExecutor()
        self.local_executor = local_executor or LocalExecutor()
        self.fail_threshold = fail_threshold
        self.health_check_interval = health_check_interval
        self._last_health_check: float = 0.0
        self._health_check_ok: bool = False
        self._health_lock = threading.Lock()

    def dispatch(self, intent: Intent) -> dict:
        """派发意图到对应执行器"""
        exe = self._route(intent.type)
        return exe.execute_safe(intent)

    def _route(self, intent_type: IntentType) -> Executor:
        """根据意图类型 + PC 健康状态选择执行器。
        Phase 1: 所有 intent 走 local（PC 路径留 _PC_INTENTS 集合，未来启用）
        """
        if intent_type in _LOCAL_INTENTS:
            return self.local_executor

        # PC 意图（未来启用）
        if self.pc_agent is not None and intent_type in _PC_INTENTS:
            if self._is_pc_healthy():
                return self.pc_agent
            return self.dev_stub

        # fallback：未分类的 intent 也走 local
        return self.local_executor

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
                self.pc_agent.reset_failures()
            return self._health_check_ok
