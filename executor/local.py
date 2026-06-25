"""LocalExecutor — RK3576 本地硬件控制（亮度/音量/应用）的真实实现。
所有 PC 端能力（Plan 1 时期走 PC agent）也路由到这里，本地优先。
"""
from __future__ import annotations
import os
import signal
import time
from executor.base import Executor, Intent, IntentType


# ── Intent 分组（避免每次 execute 都重复 if-elif 大块）──
_DISPLAY_INTENTS = frozenset({
    IntentType.SET_BRIGHTNESS, IntentType.ADJUST_BRIGHTNESS,
    IntentType.SET_CONTRAST, IntentType.ADJUST_CONTRAST,
    IntentType.SET_COLOR_TEMP, IntentType.SET_RGB_GAIN,
    IntentType.SET_INPUT, IntentType.LIST_INPUTS,
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
        if t == IntentType.LIST_VCP_CODES:
            return self._list_vcp_codes(intent)
        if t == IntentType.VOICE_START:
            return self._voice_control("start")
        if t == IntentType.VOICE_STOP:
            return self._voice_control("stop")
        if t == IntentType.VCP_READ:
            return self._vcp_read(intent)
        if t == IntentType.VCP_WRITE:
            return self._vcp_write(intent)
        if t == IntentType.MONITOR_INFO:
            return self._monitor_info(intent)
        if t == IntentType.OSD_CONTROL:
            return self._osd_control(intent)
        if t == IntentType.DISPLAY_CONFIG:
            return self._display_config(intent)
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
            return LocalExecutor._set_contrast(intent.params.get("value", 50))
        if t == IntentType.ADJUST_CONTRAST:
            return LocalExecutor._adjust_contrast(intent.params.get("delta", 0))
        if t == IntentType.SET_COLOR_TEMP:
            return LocalExecutor._set_color_temp(intent)
        if t == IntentType.SET_RGB_GAIN:
            return LocalExecutor._set_rgb_gain(intent)
        if t == IntentType.SET_INPUT:
            return LocalExecutor._set_input(intent.params.get("code", ""))
        if t == IntentType.LIST_INPUTS:
            return LocalExecutor._list_inputs()
        return {"ok": False, "err": f"unhandled display: {t.value}",
                "code": "ERR_UNSUPPORTED"}

    @staticmethod
    def _set_brightness(value: int) -> dict:
        v = max(0, min(100, int(value)))
        # ── DDC/CI first ──
        try:
            from linux.ddcci import set_brightness as _ddc_set_brightness, is_ddc_available
            if is_ddc_available():
                ok = _ddc_set_brightness(v)
                if ok:
                    return {"ok": True, "data": {"value": v, "via": "ddcci"}}
        except Exception:
            pass
        # ── fallback: sysfs backlight / xrandr ──
        from linux.backlight import set_backlight_value
        ok = set_backlight_value(v)
        if not ok:
            return {"ok": False, "err": "backlight unavailable", "code": "ERR_LOCAL_BACKLIGHT"}
        return {"ok": True, "data": {"value": v}}

    @staticmethod
    def _adjust_brightness(delta: int) -> dict:
        d = int(delta)
        # ── DDC/CI first ──
        try:
            from linux.ddcci import get_brightness as _ddc_get_brightness, set_brightness as _ddc_set_brightness, is_ddc_available
            if is_ddc_available():
                cur = _ddc_get_brightness()
                if cur >= 0:
                    new_val = max(0, min(100, cur + d))
                    ok = _ddc_set_brightness(new_val)
                    if ok:
                        return {"ok": True, "data": {"value": new_val, "previous": cur, "via": "ddcci"}}
        except Exception:
            pass
        # ── fallback ──
        from linux.backlight import get_backlight_value, set_backlight_value
        cur = get_backlight_value()
        if cur < 0:
            return {"ok": False, "err": "cannot read backlight", "code": "ERR_LOCAL_BACKLIGHT"}
        new_val = max(0, min(100, cur + d))
        ok = set_backlight_value(new_val)
        if not ok:
            return {"ok": False, "err": "backlight write failed", "code": "ERR_LOCAL_BACKLIGHT"}
        return {"ok": True, "data": {"value": new_val}}

    @staticmethod
    def _set_contrast(value: int) -> dict:
        v = max(0, min(100, int(value)))
        try:
            from linux.ddcci import set_contrast as _ddc_set_contrast, is_ddc_available
            if is_ddc_available():
                ok = _ddc_set_contrast(v)
                if ok:
                    return {"ok": True, "data": {"value": v, "via": "ddcci"}}
        except Exception:
            pass
        return {"ok": False, "err": "DDC/CI contrast unavailable",
                "code": "ERR_LOCAL_DISPLAY"}

    @staticmethod
    def _adjust_contrast(delta: int) -> dict:
        d = int(delta)
        try:
            from linux.ddcci import get_contrast as _ddc_get_contrast, set_contrast as _ddc_set_contrast, is_ddc_available
            if is_ddc_available():
                cur = _ddc_get_contrast()
                if cur >= 0:
                    new_val = max(0, min(100, cur + d))
                    ok = _ddc_set_contrast(new_val)
                    if ok:
                        return {"ok": True, "data": {"value": new_val,
                                                       "previous": cur, "via": "ddcci"}}
        except Exception:
            pass
        return {"ok": False, "err": "DDC/CI contrast unavailable",
                "code": "ERR_LOCAL_DISPLAY"}

    @staticmethod
    def _set_input(code: str) -> dict:
        if not code:
            return {"ok": False, "err": "需要 code 参数", "code": "ERR_LOCAL_DISPLAY"}
        try:
            from linux.ddcci import set_input_source, is_ddc_available
            if is_ddc_available():
                ok = set_input_source(code)
                if ok:
                    return {"ok": True, "data": {"code": code}}
        except Exception:
            pass
        return {"ok": False, "err": "DDC/CI 输入源切换不可用",
                "code": "ERR_UNSUPPORTED"}

    @staticmethod
    def _set_color_temp(intent: Intent) -> dict:
        """Set color temperature preset via DDC/CI VCP 0x14."""
        preset = intent.params.get("preset")  # e.g. "6500 K", "User 1"
        code = intent.params.get("code")       # e.g. 5, 11
        try:
            from linux.ddcci import set_color_preset, list_color_presets, is_ddc_available
            if is_ddc_available():
                if code is not None:
                    ok = set_color_preset(int(code))
                elif preset:
                    # Look up code from name
                    presets = {p["name"]: p["code"] for p in list_color_presets()}
                    matched_code = presets.get(preset)
                    if matched_code is None:
                        # Fuzzy match
                        for name, c in presets.items():
                            if preset.lower() in name.lower():
                                matched_code = c
                                break
                    if matched_code is None:
                        return {"ok": False, "err": f"Unknown preset: {preset}",
                                "code": "ERR_LOCAL_DISPLAY"}
                    ok = set_color_preset(matched_code)
                else:
                    return {"ok": False, "err": "Need 'preset' or 'code' param",
                            "code": "ERR_BAD_REQUEST"}
                if ok:
                    return {"ok": True, "data": {"via": "ddcci"}}
        except Exception:
            pass
        return {"ok": False, "err": "DDC/CI color preset unavailable",
                "code": "ERR_LOCAL_DISPLAY"}

    @staticmethod
    def _set_rgb_gain(intent: Intent) -> dict:
        """Set RGB gain via DDC/CI VCP 0x16/0x18/0x1A."""
        r = intent.params.get("red", 50)
        g = intent.params.get("green", 50)
        b = intent.params.get("blue", 50)
        try:
            from linux.ddcci import set_rgb_gain, is_ddc_available
            if is_ddc_available():
                results = set_rgb_gain(int(r), int(g), int(b))
                if any(results.values()):
                    return {"ok": True, "data": {"results": results, "via": "ddcci"}}
        except Exception:
            pass
        return {"ok": False, "err": "DDC/CI RGB gain unavailable",
                "code": "ERR_LOCAL_DISPLAY"}

    @staticmethod
    def _list_inputs() -> dict:
        # DDC/CI sources + xrandr outputs
        try:
            from linux.ddcci import list_input_sources, is_ddc_available
            if is_ddc_available():
                sources = list_input_sources()
            else:
                sources = []
        except Exception:
            sources = []
        from linux.display import list_connected_outputs
        outs = list_connected_outputs()
        return {"ok": True, "data": {"xrandr_outputs": outs, "ddc_sources": sources}}

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

    # ── VCP Code Reference ──────────────────────────────
    # WebDDCUtil config (centralized VCP knowledge base)
    _VCP_API_BASE = "http://192.168.1.213:5002"
    _VCP_API_KEY = "ddc_MyF_YWHGFhDj_h8XkenfauEtgudWGF76ge6AbYBLTbo"

    @staticmethod
    def _list_vcp_codes(intent: Intent) -> dict:
        """Query WebDDCUtil for VCP code definitions.
        Optional param 'code' to filter by VCP code (hex string like '10').
        Optional param 'keyword' to search name/description.
        """
        import urllib.request as _ur
        import json as _json

        code_filter = intent.params.get("code", "").upper().lstrip("0X")
        keyword = intent.params.get("keyword", "").lower()

        try:
            url = f"{LocalExecutor._VCP_API_BASE}/api/v1/owners/1/entries"
            req = _ur.Request(url, headers={"X-API-Key": LocalExecutor._VCP_API_KEY})
            with _ur.urlopen(req, timeout=5) as resp:
                data = _json.loads(resp.read())
        except Exception as e:
            return {"ok": False, "err": f"WebDDCUtil 查询失败: {e}",
                    "code": "ERR_VCP_REF"}

        entries = []
        for e in data.get("entries", []):
            # Filter by VCP code if specified
            if code_filter and e["code_hex"].upper() != code_filter:
                continue
            # Filter by keyword if specified
            if keyword:
                name_lower = e["name"].lower()
                desc_lower = e["description"].lower()
                if keyword not in name_lower and keyword not in desc_lower:
                    continue
            entries.append({
                "vcp_code": f"0x{e['code_hex']}",
                "name": e["name"],
                "description": e["description"],
                "type": e["vcp_type"],
                "category": e.get("category_name") or e.get("category", ""),
            })

        owner = data.get("owner_name") or data.get("owner", "VESA")
        version = data.get("owner_version") or data.get("version", "")
        return {
            "ok": True,
            "data": {
                "owner": f"{owner} {version}".strip(),
                "total_matched": len(entries),
                "entries": entries,
            },
        }

    # ── Generic VCP ─────────────────────────────────────
    @staticmethod
    def _vcp_read(intent: Intent) -> dict:
        vcp = intent.params.get("code", "")
        if not vcp:
            return {"ok": False, "err": "need 'code' param", "code": "ERR_BAD_REQUEST"}
        try:
            from linux.ddcci import vcp_read, is_ddc_available
            if is_ddc_available():
                r = vcp_read(vcp)
                if r:
                    return {"ok": True, "data": r}
        except Exception:
            pass
        return {"ok": False, "err": f"VCP {vcp} unavailable", "code": "ERR_LOCAL_DISPLAY"}

    @staticmethod
    def _vcp_write(intent: Intent) -> dict:
        vcp = intent.params.get("code", "")
        val = intent.params.get("value", 0)
        if not vcp:
            return {"ok": False, "err": "need 'code' + 'value'", "code": "ERR_BAD_REQUEST"}
        try:
            from linux.ddcci import vcp_write, is_ddc_available
            if is_ddc_available():
                ok = vcp_write(vcp, int(val))
                if ok:
                    return {"ok": True, "data": {"code": vcp, "value": int(val)}}
        except Exception:
            pass
        return {"ok": False, "err": f"VCP {vcp} write failed", "code": "ERR_LOCAL_DISPLAY"}

    @staticmethod
    def _monitor_info(intent: Intent) -> dict:
        try:
            from linux.ddcci import get_monitor_info, is_ddc_available
            if is_ddc_available():
                return {"ok": True, "data": get_monitor_info()}
        except Exception:
            pass
        return {"ok": False, "err": "monitor info unavailable", "code": "ERR_LOCAL_DISPLAY"}

    @staticmethod
    def _osd_control(intent: Intent) -> dict:
        action = intent.params.get("action", "read")
        try:
            from linux.ddcci import vcp_read, vcp_write, set_osd_language, get_osd_language
            if action == "lock":
                ok = vcp_write("0xCA", 2)
            elif action == "unlock":
                ok = vcp_write("0xCA", 1)
            elif action == "set_lang":
                ok = set_osd_language(int(intent.params.get("code", 2)))
            elif action == "read":
                r = vcp_read("0xCA")
                lang = get_osd_language()
                return {"ok": True, "data": {"osd": r, "language": lang}}
            else:
                return {"ok": False, "err": f"unknown action: {action}"}
            if ok:
                return {"ok": True, "data": {"action": action}}
        except Exception as e:
            pass
        return {"ok": False, "err": "OSD control failed", "code": "ERR_LOCAL_DISPLAY"}

    @staticmethod
    def _display_config(intent: Intent) -> dict:
        what = intent.params.get("what", "read")
        try:
            from linux.ddcci import (set_display_scaling, get_display_scaling,
                                      set_audio_mute, get_audio_mute,
                                      set_display_mode, get_display_mode, vcp_read, vcp_write)
            if what == "scaling":
                val = intent.params.get("value")
                if val is not None:
                    return {"ok": set_display_scaling(int(val)), "data": {"scaling": int(val)}}
                r = get_display_scaling()
                return {"ok": bool(r), "data": r or {}}
            elif what == "mute":
                mute = intent.params.get("mute", True)
                blank = intent.params.get("blank", False)
                if "mute" in intent.params:
                    ok = set_audio_mute(mute, blank)
                    return {"ok": ok, "data": {"mute": mute, "blank": blank}}
                r = get_audio_mute()
                return {"ok": bool(r), "data": r or {}}
            elif what == "mode":
                val = intent.params.get("value")
                if val is not None:
                    return {"ok": set_display_mode(int(val)), "data": {"mode": int(val)}}
                r = get_display_mode()
                return {"ok": bool(r), "data": r or {}}
            elif what == "volume":
                val = intent.params.get("value")
                if val is not None:
                    # AOC 0x62: 100=mute, 0=unmute. Values 0-100 pass directly.
                    return {"ok": vcp_write("0x62", int(val)),
                            "data": {"volume": int(val)}}
                r = vcp_read("0x62")
                return {"ok": bool(r), "data": r or {}}
            return {"ok": False, "err": f"unknown: {what}"}
        except Exception as e:
            return {"ok": False, "err": str(e), "code": "ERR_LOCAL_DISPLAY"}

    # ── Voice Assistant Control ─────────────────────────
    @staticmethod
    def _voice_control(action: str) -> dict:
        """Start/stop voice_assistant.py daemon."""
        import subprocess
        pid_file = "/tmp/voice_assistant.pid"
        va_script = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "voice_assistant.py",
        )

        if action == "start":
            # Check if already running
            try:
                with open(pid_file) as f:
                    old_pid = int(f.read().strip())
                os.kill(old_pid, 0)  # check if alive
                return {"ok": True, "data": {"status": "already_running", "pid": old_pid}}
            except (OSError, FileNotFoundError, ValueError):
                pass

            try:
                # Start in background via shell script (avoids fork timeout)
                start_script = os.path.join(
                    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                    "scripts", "start-voice-assistant.sh",
                )
                subprocess.Popen(
                    ["bash", start_script, "start"],
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                )
                time.sleep(1.5)  # wait for daemon to write pid file
                try:
                    with open(pid_file) as f:
                        new_pid = int(f.read().strip())
                    os.kill(new_pid, 0)
                    return {"ok": True, "data": {"status": "started", "pid": new_pid}}
                except (FileNotFoundError, ProcessLookupError, ValueError):
                    return {"ok": False, "err": "Started but process not found — check logs",
                            "code": "ERR_VOICE"}
            except Exception as e:
                return {"ok": False, "err": f"Failed to start: {e}", "code": "ERR_VOICE"}

        elif action == "stop":
            try:
                with open(pid_file) as f:
                    pid = int(f.read().strip())
                os.kill(pid, signal.SIGTERM)
                os.unlink(pid_file)
                return {"ok": True, "data": {"status": "stopped", "pid": pid}}
            except FileNotFoundError:
                return {"ok": True, "data": {"status": "not_running"}}
            except ProcessLookupError:
                return {"ok": True, "data": {"status": "already_stopped"}}
            except Exception as e:
                return {"ok": False, "err": str(e), "code": "ERR_VOICE"}

        return {"ok": False, "err": "invalid action", "code": "ERR_VOICE"}

    # ── Local backlight (legacy) ────────────────────────
    @staticmethod
    def _local_backlight(intent: Intent) -> dict:
        if intent.type == IntentType.SET_LOCAL_BACKLIGHT:
            return LocalExecutor._set_brightness(intent.params.get("value", 50))
        if intent.type == IntentType.ADJUST_LOCAL_BACKLIGHT:
            return LocalExecutor._adjust_brightness(intent.params.get("delta", 0))
        return {"ok": False, "err": "unhandled local_backlight", "code": "ERR_UNSUPPORTED"}