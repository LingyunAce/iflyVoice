"""dev_stub 执行器 — 仅用于 dev/单测，永远不会用于生产"""
from __future__ import annotations
from typing import Any
from executor.base import Executor, Intent, IntentType


class DevStubExecutor(Executor):
    """假实现：记录调用、维护一个内部状态、返回固定 ok。
    用于：
      - 单测（验证业务逻辑是否正确调度了 executor）
      - 离线开发（没 Win PC 时让 voice_pipeline 跑得通）
    """

    def __init__(self):
        self._local_state = {
            "backlight": 0,
        }
        self._call_log: list[dict] = []

    def execute(self, intent: Intent) -> dict:
        self._call_log.append(intent.to_dict())

        if intent.type == IntentType.SET_BRIGHTNESS:
            return {"ok": True, "data": {"actual": intent.params["value"], "note": "fake pc_agent"}}

        if intent.type == IntentType.ADJUST_BRIGHTNESS:
            return {"ok": True, "data": {"delta": intent.params["delta"], "note": "fake pc_agent"}}

        if intent.type == IntentType.SET_CONTRAST:
            return {"ok": True, "data": {"actual": intent.params["value"], "note": "fake"}}

        if intent.type == IntentType.ADJUST_CONTRAST:
            return {"ok": True, "data": {"delta": intent.params["delta"], "note": "fake"}}

        if intent.type == IntentType.SET_COLOR_TEMP:
            return {"ok": True, "data": {"actual": intent.params["value"], "note": "fake"}}

        if intent.type == IntentType.SET_INPUT:
            return {"ok": True, "data": {"name": f"0x{intent.params.get('code', 0):02X}", "note": "fake"}}

        if intent.type == IntentType.LIST_INPUTS:
            return {"ok": True, "data": {"current": "HDMI1", "supported": ["HDMI1", "DP1"], "note": "fake"}}

        if intent.type == IntentType.SET_VOLUME:
            return {"ok": True, "data": {"actual": intent.params["value"], "note": "fake"}}

        if intent.type == IntentType.ADJUST_VOLUME:
            return {"ok": True, "data": {"delta": intent.params["delta"], "note": "fake"}}

        if intent.type == IntentType.LAUNCH_APP:
            return {"ok": True, "data": {"name": intent.params["name"], "pid": 99999, "note": "fake"}}

        if intent.type == IntentType.CLOSE_APP:
            return {"ok": True, "data": {"name": intent.params.get("name", ""), "note": "fake"}}

        if intent.type == IntentType.FOCUS_APP:
            return {"ok": True, "data": {"name": intent.params.get("name", ""), "note": "fake"}}

        if intent.type == IntentType.LIST_APPS:
            return {"ok": True, "data": {"apps": [{"name": "微信", "path": "/fake/wechat.exe"}], "note": "fake"}}

        if intent.type == IntentType.BILIBILI_SEARCH:
            return {"ok": True, "data": {"results": [{"bvid": "BV_FAKE", "title": f"fake: {intent.params.get('keyword', '')}"}], "note": "fake"}}

        if intent.type == IntentType.ADJUST_LOCAL_BACKLIGHT:
            self._local_state["backlight"] = max(0, min(100, self._local_state["backlight"] + intent.params["delta"]))
            return {"ok": True, "data": {"actual": self._local_state["backlight"]}}

        if intent.type == IntentType.SET_LOCAL_BACKLIGHT:
            self._local_state["backlight"] = max(0, min(100, intent.params["value"]))
            return {"ok": True, "data": {"actual": self._local_state["backlight"]}}

        return {"ok": False, "err": f"dev_stub 不支持 {intent.type.value}", "code": "ERR_INTERNAL"}

    def get_local_state(self) -> dict:
        return dict(self._local_state)

    def get_call_log(self) -> list[dict]:
        return list(self._call_log)
