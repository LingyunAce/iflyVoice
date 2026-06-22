"""app_manager_linux.py 单测 — mock subprocess"""
from unittest.mock import patch, MagicMock
import subprocess


def test_launch_app_uses_xdg_open_for_known_app():
    """已知应用名（不在文件系统）走 xdg-open 兜底"""
    from app_manager_linux import launch_app
    with patch("app_manager_linux.subprocess") as m_sub, \
         patch("app_manager_linux._which", return_value="/usr/bin/xdg-open"):
        result = launch_app("firefox")
    assert result["ok"] is True
    m_sub.Popen.assert_called_once()
    args = m_sub.Popen.call_args[0][0]
    assert "xdg-open" in args or "firefox" in args


def test_launch_app_returns_error_for_nonexistent():
    """完全找不到的应用返回错误"""
    from app_manager_linux import launch_app
    with patch("app_manager_linux.subprocess") as m_sub, \
         patch("app_manager_linux._find_desktop_entry", return_value=None), \
         patch("app_manager_linux._find_binary", return_value=None), \
         patch("app_manager_linux._xdg_open_fallback", return_value=False):
        result = launch_app("完全不存在的应用xyz123")
    assert result["ok"] is False
    assert result["code"] == "ERR_APP_NOT_FOUND"


def test_close_app_kills_process_by_pid():
    """close_app 找到 PID 后 SIGTERM, sleep 1s, SIGKILL（每 PID 2 calls，共 4 calls）"""
    from app_manager_linux import close_app
    with patch("app_manager_linux._find_pids_by_name", return_value=[1234, 5678]), \
         patch("app_manager_linux.subprocess.run") as m_run, \
         patch("app_manager_linux.time.sleep"):  # mock sleep 加速测试
        m_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
        result = close_app("firefox")
    assert result["ok"] is True
    # 2 PIDs × 2 phases (SIGTERM + SIGKILL) = 4 calls
    assert m_run.call_count == 4
    # 校验所有 calls 都是 kill 命令
    for call in m_run.call_args_list:
        args = call[0][0]
        assert args[0] == "kill"
        assert args[1] in ("-TERM", "-KILL")


def test_focus_app_uses_wmctrl_when_available():
    """focus_app 用 wmctrl 切窗口"""
    from app_manager_linux import focus_app
    with patch("app_manager_linux._which", return_value="/usr/bin/wmctrl"), \
         patch("app_manager_linux.subprocess.run") as m_run:
        m_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
        result = focus_app("firefox")
    assert result["ok"] is True
    args = m_run.call_args[0][0]
    assert any("wmctrl" in a for a in args)
    assert "-a" in args


def test_list_apps_returns_running_gui_processes():
    """list_apps 调 ps 取进程列表"""
    from app_manager_linux import list_apps
    with patch("app_manager_linux.subprocess.run") as m_run:
        m_run.return_value = MagicMock(
            returncode=0,
            stdout="1234 firefox\n5678 gnome-terminal\n",
            stderr="",
        )
        result = list_apps()
    assert result["ok"] is True
    names = [a["name"] for a in result["data"]]
    assert "firefox" in names
    assert "gnome-terminal" in names