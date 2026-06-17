"""LocalExecutor — RK3576 local operations (backlight etc.) real implementation.
Currently only backlight; Plan 3+ may add mic_gain / led etc.
"""
from __future__ import annotations
from executor.base import Executor, Intent, IntentType


class LocalExecutor(Executor):
    """Real implementation for LOCAL intents. Routed here by dispatcher."""

    def execute(self, intent: Intent) -> dict:
        if intent.type == IntentType.SET_LOCAL_BACKLIGHT:
            return self._set_backlight(intent.params.get("value", 50))

        if intent.type == IntentType.ADJUST_LOCAL_BACKLIGHT:
            return self._adjust_backlight(intent.params.get("delta", 0))

        return {"ok": False, "err": f"local_executor does not support {intent.type.value}", "code": "ERR_INTERNAL"}

    @staticmethod
    def _set_backlight(value: int) -> dict:
        from linux.backlight import set_backlight_value
        ok = set_backlight_value(value)
        if not ok:
            return {"ok": False, "err": "backlight unavailable", "code": "ERR_BACKLIGHT_UNAVAILABLE"}
        return {"ok": True, "data": {"value": max(0, min(100, int(value)))}}

    @staticmethod
    def _adjust_backlight(delta: int) -> dict:
        from linux.backlight import get_backlight_value, set_backlight_value
        cur = get_backlight_value()
        if cur < 0:
            return {"ok": False, "err": "cannot read backlight", "code": "ERR_BACKLIGHT_UNAVAILABLE"}
        new_val = max(0, min(100, cur + delta))
        ok = set_backlight_value(new_val)
        if not ok:
            return {"ok": False, "err": "backlight write failed", "code": "ERR_BACKLIGHT_UNAVAILABLE"}
        return {"ok": True, "data": {"value": new_val}}
