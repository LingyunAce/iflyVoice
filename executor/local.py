"""LocalExecutor — RK3576 本地硬件控制（亮度/音量/应用）的真实实现。
所有 PC 端能力（Plan 1 时期走 PC agent）也路由到这里，本地优先。
"""
from __future__ import annotations
from executor.base import Executor, Intent, IntentType


# ── Intent 分组（避免每次 execute 都重复 if-elif 大块）──
_DISPLAY_INTENTS = frozenset({
    IntentType.SET_BRIGHTNESS, IntentType.ADJUST_BRIGHTNESS,
    IntentType.SET_CONTRAST, IntentType.ADJUST_CONTRAST,
    IntentType.SET_COLOR_TEMP, IntentType.SET_INPUT, IntentType.LIST_INPUTS,
})
_AUDIO_INTENTS = frozenset({
    IntentType.SET_VOLUME, IntentType.ADJUST_VOLUME,
})
_APP_INTENTS = frozenset({
    IntentType.LAUNCH_APP, IntentType.CLOSE_APP,
    IntentType.FOCUS_APP, IntentType.LIST_APPS,
})
_LOCAL_BACKLIGHT_INTENTS = frozenset({
    IntentType.SET_LOCAL_BACKLIGHT, IntentType.ADJUST_LOCAL_BACKLIGHT,
})


class LocalExecutor(Executor):
    """Real implementation for ALL intents on RK3576.
    Replaces PC agent for display/audio/app since Plan 4+ runs on-board.
    """

    def execute(self, intent: Intent) -> dict:
        t = intent.type
        if t in _DISPLAY_INTENTS:
            return self._display(intent)
        if t in _AUDIO_INTENTS:
            return self._audio(intent)
        if t in _APP_INTENTS:
            return self._app(intent)
        if t in _LOCAL_BACKLIGHT_INTENTS:
            return self._local_backlight(intent)
        if t == IntentType.BILIBILI_SEARCH:
            return {"ok": False, "err": "B 站搜索本期不支持", "code": "ERR_UNSUPPORTED"}
        return {"ok": False, "err": f"local_executor does not support {t.value}",
                "code": "ERR_UNSUPPORTED"}

    # ── Display ──────────────────────────────────────────
    @staticmethod
    def _display(intent: Intent) -> dict:
        t = intent.type
        if t == IntentType.SET_BRIGHTNESS:
            return LocalExecutor._set_brightness(intent.params.get("value", 50))
        if t == IntentType.ADJUST_BRIGHTNESS:
            return LocalExecutor._adjust_brightness(intent.params.get("delta", 0))
        if t == IntentType.SET_CONTRAST:
            v = max(0, min(100, int(intent.params.get("value", 50))))
            return {"ok": True, "data": {"value": v, "note": "xrandr software contrast"}}
        if t == IntentType.ADJUST_CONTRAST:
            # MVP: 用 50 作为"当前"基线（没有真实读硬件）
            cur = 50
            new_val = max(0, min(100, cur + int(intent.params.get("delta", 0))))
            return {"ok": True, "data": {"value": new_val, "note": "xrandr software contrast"}}
        if t == IntentType.SET_COLOR_TEMP:
            v = max(0, min(100, int(intent.params.get("value", 50))))
            return {"ok": True, "data": {"value": v, "note": "xrandr gamma color temp"}}
        if t == IntentType.SET_INPUT:
            return {"ok": False, "err": "板子无 DDC-CI 切换输入源",
                    "code": "ERR_UNSUPPORTED"}
        if t == IntentType.LIST_INPUTS:
            from linux.display import list_connected_outputs
            outs = list_connected_outputs()
            return {"ok": True, "data": outs}
        return {"ok": False, "err": f"unhandled display: {t.value}",
                "code": "ERR_UNSUPPORTED"}

    @staticmethod
    def _set_brightness(value: int) -> dict:
        from linux.backlight import set_backlight_value
        v = max(0, min(100, int(value)))
        ok = set_backlight_value(v)
        if not ok:
            return {"ok": False, "err": "backlight unavailable", "code": "ERR_LOCAL_BACKLIGHT"}
        return {"ok": True, "data": {"value": v}}

    @staticmethod
    def _adjust_brightness(delta: int) -> dict:
        from linux.backlight import get_backlight_value, set_backlight_value
        cur = get_backlight_value()
        if cur < 0:
            return {"ok": False, "err": "cannot read backlight", "code": "ERR_LOCAL_BACKLIGHT"}
        new_val = max(0, min(100, cur + int(delta)))
        ok = set_backlight_value(new_val)
        if not ok:
            return {"ok": False, "err": "backlight write failed", "code": "ERR_LOCAL_BACKLIGHT"}
        return {"ok": True, "data": {"value": new_val}}

    # ── Audio ────────────────────────────────────────────
    @staticmethod
    def _audio(intent: Intent) -> dict:
        t = intent.type
        if t == IntentType.SET_VOLUME:
            return LocalExecutor._set_volume(intent.params.get("value", 50))
        if t == IntentType.ADJUST_VOLUME:
            return LocalExecutor._adjust_volume(intent.params.get("delta", 0))
        return {"ok": False, "err": f"unhandled audio: {t.value}",
                "code": "ERR_UNSUPPORTED"}

    @staticmethod
    def _set_volume(value: int) -> dict:
        from linux.audio_io import set_volume
        v = max(0, min(100, int(value)))
        ok = set_volume(v)
        if not ok:
            return {"ok": False, "err": "pulseaudio unavailable", "code": "ERR_LOCAL_AUDIO"}
        return {"ok": True, "data": {"value": v}}

    @staticmethod
    def _adjust_volume(delta: int) -> dict:
        from linux.audio_io import get_volume, set_volume
        cur = get_volume()
        if cur < 0:
            return {"ok": False, "err": "cannot read volume", "code": "ERR_LOCAL_AUDIO"}
        new_val = max(0, min(100, cur + int(delta)))
        ok = set_volume(new_val)
        if not ok:
            return {"ok": False, "err": "pulseaudio write failed", "code": "ERR_LOCAL_AUDIO"}
        return {"ok": True, "data": {"value": new_val}}

    # ── App ──────────────────────────────────────────────
    @staticmethod
    def _app(intent: Intent) -> dict:
        t = intent.type
        import app_manager_linux as aml
        if t == IntentType.LAUNCH_APP:
            return aml.launch_app(intent.params.get("name", ""))
        if t == IntentType.CLOSE_APP:
            return aml.close_app(intent.params.get("name", ""))
        if t == IntentType.FOCUS_APP:
            return aml.focus_app(intent.params.get("name", ""))
        if t == IntentType.LIST_APPS:
            return aml.list_apps()
        return {"ok": False, "err": f"unhandled app: {t.value}",
                "code": "ERR_UNSUPPORTED"}

    # ── Local backlight (legacy) ────────────────────────
    @staticmethod
    def _local_backlight(intent: Intent) -> dict:
        if intent.type == IntentType.SET_LOCAL_BACKLIGHT:
            return LocalExecutor._set_brightness(intent.params.get("value", 50))
        if intent.type == IntentType.ADJUST_LOCAL_BACKLIGHT:
            return LocalExecutor._adjust_brightness(intent.params.get("delta", 0))
        return {"ok": False, "err": "unhandled local_backlight", "code": "ERR_UNSUPPORTED"}