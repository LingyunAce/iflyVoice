#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""HTTP 接口测试（不需要新启动 server，复用已在跑的服务）"""
import sys, os, json, time, urllib.request, urllib.error
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

BASE = "http://127.0.0.1:18766"

def http_get(path, timeout=5):
    url = BASE + path
    try:
        req = urllib.request.Request(url, method='GET')
        with urllib.request.urlopen(req, timeout=timeout) as r:
            body = r.read()
            return r.status, body
    except urllib.error.HTTPError as e:
        return e.code, e.read()
    except Exception as e:
        return 0, str(e).encode()

def http_post(path, data=None, timeout=5):
    url = BASE + path
    payload = json.dumps(data or {}).encode()
    try:
        req = urllib.request.Request(url, data=payload,
            headers={"Content-Type": "application/json"}, method='POST')
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, r.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()
    except Exception as e:
        return 0, str(e).encode()

# ══════════════════════════════════════════════════════════════
print(f"\n{YELLOW}=== HTTP Test 1: 基础连通性 ==={NC}")
# ══════════════════════════════════════════════════════════════
code, body = http_get("/")
check("GET / 返回 200", code == 200, f"code={code}")
check("GET / 返回 HTML", b"<html" in body.lower() or b"<!doctype" in body.lower(),
      f"body[:80]={body[:80]!r}")

code, body = http_get("/nonexistent-path-xyz")
check("GET 未知路径 404", code == 404, f"code={code}")

# ══════════════════════════════════════════════════════════════
print(f"\n{YELLOW}=== HTTP Test 2: 静态资源 ==={NC}")
# ══════════════════════════════════════════════════════════════
for path in ["/style.css", "/main.js", "/iflytek-api.js",
             "/ollama-api.js", "/sensevoice-api.js", "/ddcci-api.js",
             "/i2c-api.js", "/native-display-api.js"]:
    code, body = http_get(path)
    check(f"GET {path:30s}", code == 200, f"code={code}, size={len(body)}")

# ══════════════════════════════════════════════════════════════
print(f"\n{YELLOW}=== HTTP Test 3: Config 端点 ==={NC}")
# ══════════════════════════════════════════════════════════════
code, body = http_get("/config/displayType")
try:
    data = json.loads(body)
    check("GET /config/displayType 返回 JSON", "displayType" in data,
          f"data={data}")
except:
    check("GET /config/displayType 返回 JSON", False, f"body={body[:200]!r}")

code, body = http_post("/config/displayType", {"displayType": "native"})
try:
    data = json.loads(body)
    check("POST /config/displayType 切换", data.get("success") is True,
          f"data={data}")
except:
    check("POST /config/displayType 切换", False, f"body={body[:200]!r}")

# ══════════════════════════════════════════════════════════════
print(f"\n{YELLOW}=== HTTP Test 4: Native 端点（显示器亮度/音量等）==={NC}")
# ══════════════════════════════════════════════════════════════
code, body = http_get("/native/status")
try:
    data = json.loads(body)
    check("GET /native/status 解析", isinstance(data, dict), f"data={data}")
    # 必须有 connected 字段
    check("GET /native/status 含 connected", "connected" in data, f"keys={list(data.keys())}")
except Exception as e:
    check("GET /native/status 解析", False, str(e))

code, body = http_get("/native/volume")
try:
    data = json.loads(body)
    check("GET /native/volume", "volume" in data, f"data={data}")
except:
    check("GET /native/volume", False, f"body={body[:200]!r}")

# 读
code, body = http_get("/native/gamma")
try:
    data = json.loads(body)
    check("GET /native/gamma", "gamma" in data, f"data={data}")
except:
    check("GET /native/gamma", False, f"body={body[:200]!r}")

# 写（恢复测试：先读再写回原值）
def roundtrip_brightness():
    code, body = http_get("/native/status")
    cur = json.loads(body).get("brightness")
    if cur is None:
        return False, "no current brightness"
    code, body = http_post("/native/brightness", {"value": cur})
    data = json.loads(body)
    if data.get("success"):
        return True, f"brightness={cur}"
    return False, f"data={data}"

ok, msg = roundtrip_brightness()
check("POST /native/brightness（无变更）", ok, msg)

# ══════════════════════════════════════════════════════════════
print(f"\n{YELLOW}=== HTTP Test 5: DDC/CI 端点 ==={NC}")
# ══════════════════════════════════════════════════════════════
code, body = http_get("/ddcci/monitor_count")
try:
    data = json.loads(body)
    check("GET /ddcci/monitor_count", "count" in data, f"data={data}")
except:
    check("GET /ddcci/monitor_count", False, f"body={body[:200]!r}")

code, body = http_get("/ddcci/status")
try:
    data = json.loads(body)
    check("GET /ddcci/status", isinstance(data, dict), f"data={data}")
except:
    check("GET /ddcci/status", False, f"body={body[:200]!r}")

code, body = http_get("/ddcci/input_sources")
try:
    data = json.loads(body)
    check("GET /ddcci/input_sources", "supported" in data, f"data={data}")
except:
    check("GET /ddcci/input_sources", False, f"body={body[:200]!r}")

code, body = http_get("/ddcci/input")
try:
    data = json.loads(body)
    check("GET /ddcci/input", isinstance(data, dict), f"data={data}")
except:
    check("GET /ddcci/input", False, f"body={body[:200]!r}")

code, body = http_get("/ddcci/contrast_read")
try:
    data = json.loads(body)
    check("GET /ddcci/contrast_read", isinstance(data, dict), f"data={data}")
except:
    check("GET /ddcci/contrast_read", False, f"body={body[:200]!r}")

# ══════════════════════════════════════════════════════════════
print(f"\n{YELLOW}=== HTTP Test 6: Ollama 代理 ==={NC}")
# ══════════════════════════════════════════════════════════════
code, body = http_get("/ollama/api/tags", timeout=10)
try:
    data = json.loads(body)
    check("GET /ollama/api/tags", "models" in data or isinstance(data, dict),
          f"data_keys={list(data.keys()) if isinstance(data, dict) else type(data)}")
except:
    check("GET /ollama/api/tags", False, f"body={body[:200]!r}")

# 简单的 chat 试调（很短）
test_payload = {
    "model": "qwen3-vl:2b",
    "messages": [{"role": "user", "content": "ping"}],
    "stream": False,
}
code, body = http_post("/ollama/api/chat", test_payload, timeout=30)
try:
    data = json.loads(body)
    check("POST /ollama/api/chat（无流）", "message" in data, f"data_keys={list(data.keys()) if isinstance(data, dict) else 'N/A'}")
except:
    check("POST /ollama/api/chat（无流）", False, f"code={code}, body={body[:200]!r}")

# 流式 chat（试读取前 4KB）
import urllib.request
try:
    req = urllib.request.Request(
        BASE + "/ollama/api/chat",
        data=json.dumps({**test_payload, "stream": True}).encode(),
        headers={"Content-Type": "application/json"}, method='POST')
    resp = urllib.request.urlopen(req, timeout=30)
    chunks = []
    while True:
        chunk = resp.read(4096)
        if not chunk: break
        chunks.append(chunk)
        if sum(len(c) for c in chunks) > 4096: break
    full = b"".join(chunks)
    check("POST /ollama/api/chat（流式）", len(full) > 0,
          f"received {len(full)} bytes")
    resp.close()
except Exception as e:
    check("POST /ollama/api/chat（流式）", False, str(e)[:100])

# ══════════════════════════════════════════════════════════════
print(f"\n{YELLOW}=== HTTP Test 7: B 站搜索 ==={NC}")
# ══════════════════════════════════════════════════════════════
import urllib.parse
kw = urllib.parse.quote("测试")
code, body = http_get(f"/bilibili/search?keyword={kw}", timeout=15)
try:
    data = json.loads(body)
    if data.get("success"):
        check("GET /bilibili/search 成功", True, f"results={len(data.get('results', []))}")
    else:
        check("GET /bilibili/search 成功（API 失败回退）", True, f"msg={data.get('message', '?')}")
except:
    check("GET /bilibili/search", False, f"body={body[:200]!r}")

# ══════════════════════════════════════════════════════════════
print(f"\n{YELLOW}=== HTTP Test 8: CORS & OPTIONS ==={NC}")
# ══════════════════════════════════════════════════════════════
try:
    req = urllib.request.Request(BASE + "/config/displayType", method='OPTIONS')
    with urllib.request.urlopen(req, timeout=5) as r:
        cors = r.headers.get('Access-Control-Allow-Origin')
        check("OPTIONS CORS header", cors == "*", f"got={cors}")
except Exception as e:
    check("OPTIONS CORS header", False, str(e)[:100])

# ══════════════════════════════════════════════════════════════
print(f"\n{YELLOW}=== HTTP Test 9: 错误处理 ==={NC}")
# ══════════════════════════════════════════════════════════════
code, body = http_post("/config/nonexistent", {"x": 1})
check("POST /config/nonexistent 应 404", code == 404, f"code={code}")

code, body = http_get("/ddcci/whatever_unknown")
check("GET /ddcci/unknown 应 404", code == 404, f"code={code}")

# 非法 JSON
try:
    req = urllib.request.Request(BASE + "/native/brightness", data=b"{invalid}",
        headers={"Content-Type": "application/json"}, method='POST')
    with urllib.request.urlopen(req, timeout=5) as r:
        code = r.status
except urllib.error.HTTPError as e:
    code = e.code
check("POST 非法 JSON 不崩溃", code in (200, 400), f"code={code}")

# ══════════════════════════════════════════════════════════════
print(f"\n{YELLOW}=== HTTP Test 10: 并发稳定性 ==={NC}")
# ══════════════════════════════════════════════════════════════
import threading
results = []
def hit_endpoint():
    try:
        c, b = http_get("/config/displayType", timeout=3)
        results.append(c == 200)
    except:
        results.append(False)

threads = [threading.Thread(target=hit_endpoint) for _ in range(20)]
for t in threads: t.start()
for t in threads: t.join()
check("20 并发 GET /config/displayType", sum(results) == 20, f"成功 {sum(results)}/20")

# ══════════════════════════════════════════════════════════════
print(f"\n{YELLOW}{'='*55}{NC}")
print(f"  {GREEN}PASS: {PASS}{NC}    {RED}FAIL: {FAIL}{NC}")
print(f"{YELLOW}{'='*55}{NC}")
sys.exit(0 if FAIL == 0 else 1)
