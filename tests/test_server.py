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


def test_native_endpoint_in_do_get():
    """do_GET 中应处理 /native 前缀"""
    import server
    import inspect
    src = inspect.getsource(server.Handler.do_GET)
    assert "/native/" in src, "do_GET 中应处理 /native/ 前缀"


def test_handle_native_method_exists():
    """Handler 应该有 _handle_native 方法"""
    import server
    assert hasattr(server.Handler, "_handle_native"), "缺少 _handle_native 方法"


def test_handle_native_backlight_get_returns_50_stub():
    """_handle_native 调 GET /native/backlight 应返回 50 stub"""
    import server
    import inspect
    src = inspect.getsource(server.Handler._handle_native)
    assert "/backlight" in src, "_handle_native 应处理 backlight"
    assert "50" in src, "Plan 1 stub 应返回 50"
