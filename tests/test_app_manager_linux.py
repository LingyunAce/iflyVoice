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
    """close_app 找到 PID 后 SIGTERM, sleep 1s, kill -0 探活, SIGKILL（每 PID 3 calls，共 6 calls）"""
    from app_manager_linux import close_app
    with patch("app_manager_linux._find_pids_by_name", return_value=[1234, 5678]), \
         patch("app_manager_linux.subprocess.run") as m_run, \
         patch("app_manager_linux.time.sleep"):  # mock sleep 加速测试
        m_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
        result = close_app("firefox")
    assert result["ok"] is True
    # 2 PIDs × 3 phases (SIGTERM + kill -0 + SIGKILL) = 6 calls
    assert m_run.call_count == 6
    # 校验所有 calls 都是 kill 命令
    for call in m_run.call_args_list:
        args = call[0][0]
        assert args[0] == "kill"
        assert args[1] in ("-TERM", "-0", "-KILL")


def test_close_app_returns_term_sent_and_kill_sent():
    """close_app data 应包含 term_sent + kill_sent + pids"""
    from app_manager_linux import close_app
    with patch("app_manager_linux._find_pids_by_name", return_value=[1234]), \
         patch("app_manager_linux.subprocess.run") as m_run, \
         patch("app_manager_linux.time.sleep"):
        # kill -0 返回 0（进程还活着），其他返回 0
        m_run.return_value = MagicMock(returncode=0)
        result = close_app("firefox")
    assert result["ok"] is True
    assert result["data"]["term_sent"] == 1
    assert result["data"]["kill_sent"] == 1
    assert result["data"]["pids"] == [1234]


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


def test_focus_app_returns_error_when_wmctrl_no_match():
    """focus_app: wmctrl 退出码非 0 → ERR_WINDOW_NOT_FOUND"""
    from app_manager_linux import focus_app
    with patch("app_manager_linux._which", return_value="/usr/bin/wmctrl"), \
         patch("app_manager_linux.subprocess.run") as m_run:
        m_run.return_value = MagicMock(returncode=1, stdout="", stderr="no match")
        result = focus_app("nonexistent_window_xyz")
    assert result["ok"] is False
    assert result["code"] == "ERR_WINDOW_NOT_FOUND"


def test_focus_app_returns_error_when_no_window_manager():
    """focus_app: wmctrl + xdotool 都不可用 → ERR_NO_WINDOW_MANAGER"""
    from app_manager_linux import focus_app
    with patch("app_manager_linux._which", return_value=None):
        result = focus_app("firefox")
    assert result["ok"] is False
    assert result["code"] == "ERR_NO_WINDOW_MANAGER"


def test_focus_app_falls_back_to_xdotool():
    """focus_app: wmctrl 不可用但 xdotool 可用"""
    from app_manager_linux import focus_app
    def which_side_effect(cmd):
        return "/usr/bin/xdotool" if cmd == "xdotool" else None
    with patch("app_manager_linux._which", side_effect=which_side_effect), \
         patch("app_manager_linux.subprocess.run") as m_run:
        m_run.return_value = MagicMock(returncode=0, stdout="12345", stderr="")
        result = focus_app("firefox")
    assert result["ok"] is True
    assert result["data"]["via"] == "xdotool"


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


def test_list_apps_filters_system_processes():
    """list_apps: 过滤 systemd/kworker/低 pid"""
    from app_manager_linux import list_apps
    with patch("app_manager_linux.subprocess.run") as m_run:
        m_run.return_value = MagicMock(
            returncode=0,
            stdout=(
                "1 systemd\n"
                "500 dbus-daemon\n"
                "999 kworker/0:1\n"
                "1000 firefox\n"
                "2000 gnome-terminal\n"
            ),
            stderr="",
        )
        result = list_apps()
    names = [a["name"] for a in result["data"]]
    assert "firefox" in names
    assert "gnome-terminal" in names
    assert "systemd" not in names
    assert "dbus-daemon" not in names
    assert "kworker/0:1" not in names