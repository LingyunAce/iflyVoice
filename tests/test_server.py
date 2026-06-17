"""测试 server.py 路由表。BaseHTTPRequestHandler 紧耦合 socket，改为测纯函数。"""
import json
import sys
import importlib


def test_server_module_imports():
    """server.py 能被 import（无语法错误）"""
    import server  # noqa: F401


def test_health_endpoint_defined_in_do_get():
    """do_GET 中应包含 /health 分支（先失败再补）"""
    import server
    import inspect
    src = inspect.getsource(server.Handler.do_GET)
    assert "/health" in src, "do_GET 中找不到 /health 分支"


def test_ddcci_route_removed_from_do_get():
    """do_GET 中应不再包含 /ddcci 分支"""
    import server
    import inspect
    src = inspect.getsource(server.Handler.do_GET)
    assert "/ddcci/" not in src, "do_GET 仍包含 /ddcci/，应删除"


def test_bilibili_route_removed():
    """do_GET 中应不再包含 /bilibili 分支"""
    import server
    import inspect
    src = inspect.getsource(server.Handler.do_GET)
    assert "/bilibili/" not in src, "do_GET 仍包含 /bilibili/，应删除"


def test_powershell_subprocess_removed():
    """server.py 中不应再有 'powershell' 调用"""
    import server
    import inspect
    src = inspect.getsource(server)
    assert "powershell" not in src.lower(), "server.py 仍含 PowerShell 调用"
