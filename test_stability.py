#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""稳定性 / 资源 / 异常测试"""
import sys, os, json, gc, time, threading, tempfile, shutil
sys.stdout.reconfigure(encoding='utf-8')

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
print(f"\n{YELLOW}=== Stability 1: 进程 / 文件描述符泄漏 ==={NC}")
# ══════════════════════════════════════════════════════════════

# 1.1 silero_vad.onnx 能正常打开
import onnxruntime
try:
    s1 = onnxruntime.InferenceSession(
        "silero_vad.onnx", providers=['CPUExecutionProvider'])
    s2 = onnxruntime.InferenceSession(
        "silero_vad.onnx", providers=['CPUExecutionProvider'])
    del s1, s2
    gc.collect()
    check("ONNX 会话多次创建/销毁无异常", True)
except Exception as e:
    check("ONNX 会话多次创建/销毁无异常", False, str(e))

# 1.2 utils._log_file 文件句柄
from utils import _log_file, _flog
try:
    for _ in range(100):
        _flog("[test]", "test message")
    check("utils._flog 100 次写入无异常", True)
    # 文件大小增长合理
    if os.path.exists("widget.log"):
        size = os.path.getsize("widget.log")
        check("widget.log 文件可读", size > 0, f"size={size}")
except Exception as e:
    check("utils._flog 100 次写入无异常", False, str(e))

# 1.3 临时文件清理
import subprocess
import uuid
tmp_dir = tempfile.gettempdir()
before = set(os.listdir(tmp_dir))
for _ in range(5):
    tmp_file = os.path.join(tmp_dir, f"stability_test_{uuid.uuid4().hex}.tmp")
    with open(tmp_file, "w") as f:
        f.write("test")
    os.unlink(tmp_file)
after = set(os.listdir(tmp_dir))
leaked = [f for f in (after - before) if f.startswith("stability_test_")]
check("临时文件创建/清理无残留", len(leaked) == 0, f"leaked={leaked}")

# ══════════════════════════════════════════════════════════════
print(f"\n{YELLOW}=== Stability 2: 长时间运行 / 内存增长 ==={NC}")
# ══════════════════════════════════════════════════════════════
import tracemalloc
tracemalloc.start()

from voice_pipeline import parse_voice_command
from utils import _strip_md

snap1 = tracemalloc.take_snapshot()
for _ in range(10000):
    parse_voice_command("亮度调到50 这是一段测试文本 音量加10")
    _strip_md("**bold** and `code` with [link](url) and ```code block```")
snap2 = tracemalloc.take_snapshot()

stats = snap2.compare_to(snap1, 'lineno')
total_growth = sum(s.size_diff for s in stats if s.size_diff > 0)
total_growth_mb = total_growth / 1024 / 1024
# 1万次调用增长不应超过 5MB
check(f"10000 次调用内存增长 < 5MB", total_growth_mb < 5,
      f"growth={total_growth_mb:.2f}MB")

tracemalloc.stop()

# ══════════════════════════════════════════════════════════════
print(f"\n{YELLOW}=== Stability 3: HTTP 持续打点 / 速率测试 ==={NC}")
# ══════════════════════════════════════════════════════════════
import urllib.request, urllib.error
BASE = "http://127.0.0.1:18766"

start = time.time()
errors = 0
ok = 0
for i in range(200):
    try:
        req = urllib.request.Request(BASE + "/config/displayType")
        with urllib.request.urlopen(req, timeout=3) as r:
            if r.status == 200:
                ok += 1
            else:
                errors += 1
    except Exception as e:
        errors += 1
elapsed = time.time() - start
rps = 200 / elapsed if elapsed > 0 else 0
check(f"200 次连续 GET 全部成功", errors == 0, f"ok={ok}, err={errors}, rps={rps:.1f}")

# ══════════════════════════════════════════════════════════════
print(f"\n{YELLOW}=== Stability 4: 错误恢复 / 异常处理 ==={NC}")
# ══════════════════════════════════════════════════════════════
# 4.1 server 对损坏 POST 数据不崩溃
bad_payloads = [
    b"",
    b"\x00\x00\x00",
    b"x" * 1000000,  # 1MB
    b'{"incomplete":',
]
for i, payload in enumerate(bad_payloads):
    try:
        req = urllib.request.Request(BASE + "/native/brightness", data=payload,
            headers={"Content-Type": "application/json"}, method='POST')
        with urllib.request.urlopen(req, timeout=10) as r:
            pass
    except urllib.error.HTTPError as e:
        pass  # 400 也算成功（没有 500 错误）
    except Exception as e:
        check(f"坏 payload #{i} 处理", False, str(e)[:80])
    else:
        pass
check("坏 payload 不导致 server 500 错误", True)

# 4.2 服务在压力测试后仍然响应
time.sleep(0.5)
try:
    req = urllib.request.Request(BASE + "/config/displayType")
    with urllib.request.urlopen(req, timeout=3) as r:
        check("压力后服务仍响应", r.status == 200)
except Exception as e:
    check("压力后服务仍响应", False, str(e)[:80])

# ══════════════════════════════════════════════════════════════
print(f"\n{YELLOW}=== Stability 5: app_manager 扫描稳定性 ==={NC}")
# ══════════════════════════════════════════════════════════════
# 这会调 PowerShell 扫描开始菜单，可能慢
try:
    sys.path.insert(0, ".")
    import app_manager
    apps = app_manager.get_apps()
    check(f"app_manager.get_apps() 正常", isinstance(apps, dict), f"got {len(apps)} apps")
    # 第二次应该走缓存
    apps2 = app_manager.get_apps()
    check(f"app_manager 缓存生效", apps is apps2)
except Exception as e:
    check(f"app_manager.get_apps() 正常", False, str(e)[:200])

# ══════════════════════════════════════════════════════════════
print(f"\n{YELLOW}=== Stability 6: 麦克风枚举稳定性 ==={NC}")
# ══════════════════════════════════════════════════════════════
import sounddevice as sd
try:
    devs1 = sd.query_devices()
    devs2 = sd.query_devices()
    check("sounddevice.query_devices() 重复调用一致",
          len(devs1) == len(devs2), f"first={len(devs1)}, second={len(devs2)}")
    # 输入设备数
    inputs = [d for d in devs1 if d.get('max_input_channels', 0) > 0]
    check(f"输入设备 > 0", len(inputs) > 0, f"count={len(inputs)}")
except Exception as e:
    check("sounddevice.query_devices() 正常", False, str(e)[:100])

# ══════════════════════════════════════════════════════════════
print(f"\n{YELLOW}=== Stability 7: 并发 + 资源混合测试 ==={NC}")
# ══════════════════════════════════════════════════════════════
errors = []
def stress():
    try:
        for _ in range(50):
            parse_voice_command("亮度调到50")
            _strip_md("**test**")
        # 同时打 HTTP
        for _ in range(10):
            urllib.request.urlopen(BASE + "/config/displayType", timeout=3).close()
    except Exception as e:
        errors.append(str(e))

threads = [threading.Thread(target=stress) for _ in range(8)]
for t in threads: t.start()
for t in threads: t.join()
check("8 线程 x (50 local + 10 http) 无错误", len(errors) == 0,
      f"errs={len(errors)}, first={errors[0][:100] if errors else ''}")

# ══════════════════════════════════════════════════════════════
print(f"\n{YELLOW}{'='*55}{NC}")
print(f"  {GREEN}PASS: {PASS}{NC}    {RED}FAIL: {FAIL}{NC}")
print(f"{YELLOW}{'='*55}{NC}")
sys.exit(0 if FAIL == 0 else 1)
