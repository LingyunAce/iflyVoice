"""Executor 抽象层 — 业务侧只调接口，不感知 local/remote"""
from __future__ import annotations
import re
from abc import ABC, abstractmethod
from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Optional


class IntentType(str, Enum):
    """所有可执行意图的类型枚举"""
    # 显示器控制（远端 PC 显示器）
    SET_BRIGHTNESS = "set_brightness"
    ADJUST_BRIGHTNESS = "adjust_brightness"
    SET_CONTRAST = "set_contrast"
    ADJUST_CONTRAST = "adjust_contrast"
    SET_COLOR_TEMP = "set_color_temp"
    SET_RGB_GAIN = "set_rgb_gain"
    SET_INPUT = "set_input"
    LIST_INPUTS = "list_inputs"

    # 音量（远端 PC 系统音量）
    SET_VOLUME = "set_volume"
    ADJUST_VOLUME = "adjust_volume"

    # 桌面应用（远端 PC）
    LAUNCH_APP = "launch_app"
    CLOSE_APP = "close_app"
    FOCUS_APP = "focus_app"
    LIST_APPS = "list_apps"

    # B 站搜索（远端 PC ffplay 播）
    BILIBILI_SEARCH = "bilibili_search"

    # 本机控制（RK3576 本地，不走 PC）
    ADJUST_LOCAL_BACKLIGHT = "adjust_local_backlight"
    SET_LOCAL_BACKLIGHT = "set_local_backlight"

    # 查询 VCP 码表（WebDDCUtil）
    LIST_VCP_CODES = "list_vcp_codes"

    # 语音助手控制
    VOICE_START = "voice_start"
    VOICE_STOP = "voice_stop"

    # 通用 VCP 读写
    VCP_READ = "vcp_read"
    VCP_WRITE = "vcp_write"
    MONITOR_INFO = "monitor_info"
    OSD_CONTROL = "osd_control"
    DISPLAY_CONFIG = "display_config"

    # 无意图（普通对话）
    NONE = "none"


@dataclass
class Intent:
    """意图数据类 — 业务侧产出，executor 消费"""
    type: IntentType
    params: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        d = asdict(self)
        d["type"] = self.type.value
        return d


class ExecutorError(Exception):
    """执行器统一异常"""
    pass


class Executor(ABC):
    """执行器抽象基类。子类：pc_agent（生产）、dev_stub（测试）"""

    @abstractmethod
    def execute(self, intent: Intent) -> dict:
        """执行意图，返回 {"ok": bool, ...}

        成功：{"ok": True, "data": {...}}
        失败：{"ok": False, "err": "...", "code": "ERR_XXX"}
        """
        raise NotImplementedError

    def execute_safe(self, intent: Intent) -> dict:
        """执行意图，捕获异常并包装为标准错误格式"""
        try:
            return self.execute(intent)
        except ExecutorError as e:
            return {"ok": False, "err": str(e), "code": "ERR_INTERNAL"}
        except Exception as e:
            return {"ok": False, "err": str(e), "code": "ERR_INTERNAL"}


# ── 文本→意图 解析 ─────────────────────────────────────
# 复用现有 voice_pipeline.parse_voice_command 的正则逻辑，但产出 Intent 而非 dict


def parse_intent_from_voice_text(text: str) -> Optional[Intent]:
    """从 ASR 文本解析意图。返回 Intent 或 None（普通对话）。"""
    if not text:
        return None
    t = text.lower().strip()
    raw = text.strip()

    # ── 本机屏控制（明确说"本机/自己"） ──
    if re.search(r'(?:本机|自己|这个)(?:屏幕|显示器|屏).*(?:亮一点|再亮点|更亮|亮一些)', t):
        return Intent(IntentType.ADJUST_LOCAL_BACKLIGHT, {"delta": 10})
    if re.search(r'(?:本机|自己|这个)(?:屏幕|显示器|屏).*(?:暗一点|再暗点|更暗|暗一些)', t):
        return Intent(IntentType.ADJUST_LOCAL_BACKLIGHT, {"delta": -10})

    # ── 亮度 ──
    m = re.search(r'(?:把\s*)?亮度\s*(?:调|设)(?:高|大|亮|低|小|暗)?(?:成|为|到|整?到)\s*(\d{1,3})%?', t)
    if not m:
        m = re.search(r'(?:亮度|屏幕)\s*[:：]?\s*(\d{1,3})%?', t)
    if m:
        v = max(0, min(100, int(m.group(1))))
        return Intent(IntentType.SET_BRIGHTNESS, {"value": v, "monitor_index": 0})

    if re.search(r'(?:亮度|屏幕)\s*(?:调|设)?(?:成|为|到)?\s*(?:最高|最大|最亮|full)', t):
        return Intent(IntentType.SET_BRIGHTNESS, {"value": 100, "monitor_index": 0})
    if re.search(r'(?:亮度|屏幕)\s*(?:调|设)?(?:成|为|到)?\s*(?:最低|最小|最暗)', t):
        return Intent(IntentType.SET_BRIGHTNESS, {"value": 0, "monitor_index": 0})

    m = re.search(r'(?:亮度|屏幕)\s*(?:调|设)?(?:高|大|亮)\s*(\d{1,3})', t)
    if m:
        return Intent(IntentType.ADJUST_BRIGHTNESS, {"delta": int(m.group(1)), "monitor_index": 0})
    m = re.search(r'(?:亮度|屏幕)\s*(?:调|设)?(?:低|小|暗)\s*(\d{1,3})', t)
    if m:
        return Intent(IntentType.ADJUST_BRIGHTNESS, {"delta": -int(m.group(1)), "monitor_index": 0})

    # ── 音量 ──
    m = re.search(r'音量\s*(?:调|设)(?:高|大|低|小)?(?:成|为|到|整?到)\s*(\d{1,3})%?', t)
    if m:
        return Intent(IntentType.SET_VOLUME, {"value": max(0, min(100, int(m.group(1))))})
    m = re.search(r'音量\s*(?:调|设)?(?:高|大)\s*(\d{1,3})', t)
    if m:
        return Intent(IntentType.ADJUST_VOLUME, {"delta": int(m.group(1))})
    m = re.search(r'音量\s*(?:调|设)?(?:低|小)\s*(\d{1,3})', t)
    if m:
        return Intent(IntentType.ADJUST_VOLUME, {"delta": -int(m.group(1))})
    if re.search(r'音量.*(?:大点|大一些|大声|大声点)', t):
        return Intent(IntentType.ADJUST_VOLUME, {"delta": 10})
    if re.search(r'音量.*(?:小点|小一些|小声|小声点)', t):
        return Intent(IntentType.ADJUST_VOLUME, {"delta": -10})

    # ── 应用控制 ──
    m = re.search(r'打开\s*(.+)', raw)
    if m:
        return Intent(IntentType.LAUNCH_APP, {"name": m.group(1).strip()})
    m = re.search(r'关闭\s*(.+)', raw)
    if m:
        return Intent(IntentType.CLOSE_APP, {"name": m.group(1).strip()})
    m = re.search(r'切换到\s*(.+)', raw)
    if m:
        return Intent(IntentType.FOCUS_APP, {"name": m.group(1).strip()})

    # ── B 站 ──
    # 形如 "B站搜索 XXX" / "搜索 B站 XXX" / "在B站上播放 XXX"
    m = re.search(r'(?:搜索|找|播放|听)\s*(?:.*?)?(?:B站|哔哩哔哩|bilibili|b站)\s*(?:.*?)(\S.+)', raw)
    if m:
        kw = m.group(1).strip()
        if kw:
            return Intent(IntentType.BILIBILI_SEARCH, {"keyword": kw})
    m = re.search(r'(?:B站|哔哩哔哩|bilibili|b站)\s*(?:搜索|找|播放|听)\s*(\S.+)', raw)
    if m:
        kw = m.group(1).strip()
        if kw:
            return Intent(IntentType.BILIBILI_SEARCH, {"keyword": kw})
    m = re.search(r'(?:B站|哔哩哔哩|bilibili|b站)\s*(.+)', raw)
    if m:
        kw = m.group(1).strip()
        if kw and not re.search(r'打开|关闭', kw):
            return Intent(IntentType.BILIBILI_SEARCH, {"keyword": kw})

    return None
