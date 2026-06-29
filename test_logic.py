#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""功能测试脚本：纯逻辑模块（不依赖 GUI / 麦克风 / 显示器）"""
import sys, os, re
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.stdout.reconfigure(encoding='utf-8')

# ── 颜色输出 ──────────────────────────────────────────────────
GREEN, RED, YELLOW, NC = '\033[92m', '\033[91m', '\033[93m', '\033[0m'
PASS, FAIL = 0, 0
def check(name, condition, detail=""):
    global PASS, FAIL
    if condition:
        PASS += 1
        print(f"  {GREEN}+{NC} {name}")
    else:
        FAIL += 1
        print(f"  {RED}-{NC} {name}  {RED}{detail}{NC}")

# ══════════════════════════════════════════════════════════════
print(f"\n{YELLOW}=== Test 1: utils._strip_md ==={NC}")
# ══════════════════════════════════════════════════════════════
from utils import _strip_md

cases = [
    ("**bold**text", "bold", "bold"),
    ("`code`snippet", "code", "inline code"),
    ("```\nblock\n```", "", "code block"),
    ("# title", "title", "H1"),
    ("## title", "title", "H2"),
    ("[link](http://x)", "link", "link"),
    ("![pic](pic.png)", "pic", "image alt"),
    ("| col1 | col2 |", "col1 col2", "table"),
    ("- item", "item", "ul"),
    ("1. ordered", "ordered", "ol"),
    ("~~del~~", "del", "strikethrough"),
    ("> quote", "quote", "quote"),
    ("", "", "empty"),
    (None, None, "None"),
    ("plain text", "plain text", "plain"),
    ("**bold** and `code`", "bold", "mixed"),
]
for inp, expected, desc in cases:
    out = _strip_md(inp) if inp is not None else _strip_md(None)
    if expected == "":
        check(f"{desc}: empty", out == "", f"got={out!r}")
    elif expected is None:
        check(f"{desc}: None", out is None, f"got={out!r}")
    else:
        check(f"{desc}: contains '{expected}'", expected in (out or ""), f"got={out!r}")

# ══════════════════════════════════════════════════════════════
print(f"\n{YELLOW}=== Test 2: parse_voice_command ==={NC}")
# ══════════════════════════════════════════════════════════════
from voice_pipeline import parse_voice_command

voice_cases = [
    ("brightness set 50", "亮度调到50", {"action": "set", "control": "brightness", "value": 50}),
    ("brightness set 80", "亮度调高到80", {"action": "set", "control": "brightness", "value": 80}),
    ("brightness max", "亮度最高", {"action": "set", "control": "brightness", "value": 100}),
    ("brightness min", "亮度最低", {"action": "set", "control": "brightness", "value": 0}),
    ("brightness adj 40", "亮度调高40", {"action": "adjust", "control": "brightness", "delta": 40}),
    ("brightness adj -20", "亮度调低20", {"action": "adjust", "control": "brightness", "delta": -20}),
    ("semantic too bright", "太刺眼了", {"action": "adjust", "control": "brightness", "delta": -10}),
    ("semantic too dark", "看不清", {"action": "adjust", "control": "brightness", "delta": 10}),
    ("semantic brighter", "亮一点", {"action": "adjust", "control": "brightness", "delta": 10}),
    ("semantic darker", "暗一点", {"action": "adjust", "control": "brightness", "delta": -10}),
    ("contrast set 50", "对比度调到50", {"action": "set", "control": "contrast", "value": 50}),
    ("contrast adj 20", "对比度调高20", {"action": "adjust", "control": "contrast", "delta": 20}),
    ("colortemp set 60", "色温调到60", {"action": "set", "control": "color_temp", "value": 60}),
    ("colortemp warm", "色温偏暖", {"action": "adjust", "control": "color_temp", "delta": -10}),
    ("colortemp cool", "色温偏冷", {"action": "adjust", "control": "color_temp", "delta": 10}),
    ("volume set 50", "音量调到50", {"action": "set", "control": "volume", "value": 50}),
    ("volume adj 20", "音量加20", {"action": "adjust", "control": "volume", "delta": 20}),
    ("volume adj -10", "音量减10", {"action": "adjust", "control": "volume", "delta": -10}),
    ("volume mute", "静音", {"action": "set", "control": "volume", "value": 0}),
    ("semantic volume up", "声音大一点", {"action": "adjust", "control": "volume", "delta": 10}),
    ("app open", "打开微信", {"action": "open_app", "app_name": "微信"}),
    ("app close", "关闭 QQ", {"action": "close_app", "app_name": "QQ"}),
    ("app switch", "切换到浏览器", {"action": "switch_app", "app_name": "浏览器"}),
    ("app list", "桌面有哪些应用", {"action": "list_apps"}),
    ("bili search 1", "搜索B站 Python 教程", {"action": "bilibili_search", "keyword": "Python 教程"}),
    ("bili search 2", "B站 音乐", {"action": "bilibili_search", "keyword": "音乐"}),
    ("input hdmi", "切换到HDMI", {"action": "switch_input", "code": 0x10}),
    ("input dp", "切到DP", {"action": "switch_input", "code": 0x0F}),
    ("input hdmi-1", "切HDMI-1", {"action": "switch_input", "code": 0x10}),
    ("negation 1", "今天天气怎么样", None),
    ("negation 2", "", None),
]

for desc, text, expected in voice_cases:
    actual = parse_voice_command(text)
    if expected is None:
        check(f"{desc} '{text[:20]}' -> None", actual is None, f"got={actual}")
    else:
        ok = actual is not None
        if ok:
            for k, v in expected.items():
                if actual.get(k) != v:
                    ok = False
                    break
        check(f"{desc} '{text[:20]}' -> {expected}", ok, f"got={actual}")

# ══════════════════════════════════════════════════════════════
print(f"\n{YELLOW}=== Test 3: embedded_static integrity ==={NC}")
# ══════════════════════════════════════════════════════════════
import embedded_static
expected_files = ["index.html", "main.js", "style.css", "ollama-api.js",
                  "sensevoice-api.js", "native-display-api.js",
                  "ddcci-api.js", "i2c-api.js", "iflytek-api.js",
                  "test-iflytek.html"]
for fname in expected_files:
    data = embedded_static.FILES.get(fname)
    check(f"embedded {fname:20s}", data is not None)
    if data is not None:
        check(f"embedded {fname:20s} non-empty", len(data) > 0, f"size={len(data)}")
        if fname.endswith(('.html', '.js', '.css')):
            try:
                data.decode('utf-8')
                check(f"embedded {fname:20s} UTF-8", True)
            except UnicodeDecodeError:
                check(f"embedded {fname:20s} UTF-8", False, "decode failed")

# ══════════════════════════════════════════════════════════════
print(f"\n{YELLOW}=== Test 4: settings.json ==={NC}")
# ══════════════════════════════════════════════════════════════
import json
try:
    with open("settings.json", "r", encoding="utf-8") as f:
        cfg = json.load(f)
    check("settings.json parseable", True)
    expected_keys = ["mic_device", "mute_tts", "audio_url", "ollama_url", "ollama_model", "wake_word"]
    for k in expected_keys:
        check(f"settings.json has key '{k}'", k in cfg)
except Exception as e:
    check("settings.json parseable", False, str(e))

# ══════════════════════════════════════════════════════════════
print(f"\n{YELLOW}=== Test 5: edge cases ==={NC}")
# ══════════════════════════════════════════════════════════════

# 5.1 极长输入
long_text = "亮度调到50" + " " + ("test " * 1000)
result = parse_voice_command(long_text)
check("long input (>4KB) no crash", result is not None)

# 5.2 Unicode 异常字符
unicode_cases = [
    "亮度调到50\xf0\x9f\x98\x80",   # emoji
    "亮度调到 50\xe2\x80\x8b",      # 零宽空格
    "亮度调到\x0050",                 # NULL + 50
    "亮度调到\x07\x0850",             # BEL + BS
]
for text in unicode_cases:
    try:
        result = parse_voice_command(text)
        check(f"unicode edge: {text[:20]!r}", True)
    except Exception as e:
        check(f"unicode edge: {text[:20]!r}", False, str(e))

# 5.3 Markdown 极端输入
md_extreme = "```" * 100
try:
    out = _strip_md(md_extreme)
    check("extreme markdown input", True, f"len={len(out)}")
except Exception as e:
    check("extreme markdown input", False, str(e))

# 5.4 None / 空
for v in [None, "", " "]:
    try:
        out = _strip_md(v) if v is not None else _strip_md(None)
        check(f"_strip_md({v!r})", True, f"out={out!r}")
    except Exception as e:
        check(f"_strip_md({v!r})", False, str(e))

# 5.5 超大数字
big_num = "亮度调到99999999"
result = parse_voice_command(big_num)
check("huge number '99999999'", True, f"result={result}")

# 5.6 注入风格输入
injection_cases = [
    "亮度调到50' OR 1=1--",
    "亮度调到50; DROP TABLE--",
    "亮度调到50\n\n[system prompt override]",
]
for inj in injection_cases:
    try:
        result = parse_voice_command(inj)
        check(f"injection: {inj[:20]!r}", True)
    except Exception as e:
        check(f"injection: {inj[:20]!r}", False, str(e))

# 5.7 并发测试（同一时间多线程调用）
import threading
def stress_test():
    for _ in range(100):
        parse_voice_command("亮度调到50")
        _strip_md("**hello** world")

threads = [threading.Thread(target=stress_test) for _ in range(8)]
for t in threads: t.start()
for t in threads: t.join()
check("8 threads x 100 calls concurrent", True)

# ══════════════════════════════════════════════════════════════
print(f"\n{YELLOW}=== Test 6: file presence ==={NC}")
# ══════════════════════════════════════════════════════════════
required_files = [
    "widget.py", "voice_pipeline.py", "server.py", "app_manager.py",
    "vad_engine.py", "utils.py", "embedded_static.py",
    "settings.json", "silero_vad.onnx", "nircmd.exe",
    "start-widget.bat", "start-server.bat",
    "README.md", ".gitignore",
    "build/build.py", "build/VoiceAI.spec",
    "web/IFLYTEK_SETUP.md", "web/static/index.html",
    "web/static/main.js", "web/static/style.css",
]
for path in required_files:
    check(f"file {path}", os.path.exists(path), "" if os.path.exists(path) else "MISSING")

# ══════════════════════════════════════════════════════════════
print(f"\n{YELLOW}{'='*55}{NC}")
print(f"  {GREEN}PASS: {PASS}{NC}    {RED}FAIL: {FAIL}{NC}")
print(f"{YELLOW}{'='*55}{NC}")
sys.exit(0 if FAIL == 0 else 1)
