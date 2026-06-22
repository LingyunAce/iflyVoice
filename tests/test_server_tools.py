"""server.py /api/v1/tools/* 端点测试 — 启动真实 HTTP server 后用 urllib 调"""
import json
import os
import socket
import subprocess
import sys
import time
import urllib.request
import urllib.error


def _find_free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _wait_port(port, timeout=5.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.5):
                return True
        except OSError:
            time.sleep(0.1)
    return False


def _post_json(port, path, payload, timeout=5):
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        f"http://127.0.0.1:{port}{path}",
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, json.loads(resp.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read() or b"{}")


def _get_json(port, path, timeout=5):
    req = urllib.request.Request(f"http://127.0.0.1:{port}{path}", method="GET")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, json.loads(resp.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read() or b"{}")


def test_health_endpoint():
    port = _find_free_port()
    proc = subprocess.Popen(
        [sys.executable, "server.py", "--port", str(port)],
        cwd=os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    try:
        assert _wait_port(port), "server did not start"
        code, body = _get_json(port, "/health")
        assert code == 200
        assert body.get("ok") is True
    finally:
        proc.terminate()
        proc.wait(timeout=5)


def test_set_brightness_endpoint_routes_correctly():
    """POST /api/v1/tools/set_brightness 路由到 dispatcher 并返回结构化响应。

    注意：monkeypatch 不跨 subprocess 边界，所以不能在测试进程 mock。
    这里只验证路由：status 是 2xx/4xx（不是 500），body 是结构化 dict
    且含 'ok' 键。具体执行结果依赖 linux.backlight，在 Windows 上自然失败。
    """
    port = _find_free_port()
    proc = subprocess.Popen(
        [sys.executable, "server.py", "--port", str(port)],
        cwd=os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    try:
        assert _wait_port(port)
        code, body = _post_json(port, "/api/v1/tools/set_brightness", {"value": 60})
        # 路由成功：200 (执行成功) 或 400 (执行失败但路由正确) — 都不是 500
        assert code in (200, 400), f"unexpected status {code}"
        assert isinstance(body, dict)
        assert "ok" in body
        # 必须是结构化错误或成功（不是异常）
        if not body["ok"]:
            assert "code" in body  # 失败时必有 code
    finally:
        proc.terminate()
        proc.wait(timeout=5)


def test_list_apps_endpoint_routes():
    """GET /api/v1/tools/list_apps 路由到 LIST_APPS intent"""
    port = _find_free_port()
    proc = subprocess.Popen(
        [sys.executable, "server.py", "--port", str(port)],
        cwd=os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    try:
        assert _wait_port(port)
        code, body = _get_json(port, "/api/v1/tools/list_apps")
        assert code in (200, 400)
        assert isinstance(body, dict)
        assert "ok" in body
    finally:
        proc.terminate()
        proc.wait(timeout=5)


def test_unknown_endpoint_returns_404():
    port = _find_free_port()
    proc = subprocess.Popen(
        [sys.executable, "server.py", "--port", str(port)],
        cwd=os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    try:
        assert _wait_port(port)
        code, body = _post_json(port, "/api/v1/tools/unknown_tool", {})
        assert code == 404
        assert body["ok"] is False
    finally:
        proc.terminate()
        proc.wait(timeout=5)