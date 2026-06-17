"""Display output query (xrandr wrapper)"""
from __future__ import annotations
import re
import subprocess
from typing import Optional


def _run_xrandr() -> str:
    """Run xrandr --query, return stdout (empty string on error)"""
    try:
        result = subprocess.run(
            ["xrandr", "--query"],
            capture_output=True, text=True, timeout=2,
        )
        return result.stdout
    except Exception:
        return ""


def list_connected_outputs() -> list[str]:
    """List all connected outputs (HDMI-1, DP-1, ...)"""
    out = _run_xrandr()
    if not out:
        return []
    pattern = re.compile(r"^(\S+)\s+connected", re.MULTILINE)
    return pattern.findall(out)


def get_current_resolution(output: str) -> Optional[tuple[int, int]]:
    """Get current resolution (W, H) for specified output"""
    out = _run_xrandr()
    if not out:
        return None
    # Find "OUTPUT connected ... WxH+..." or "OUTPUT connected primary WxH+..."
    pattern = re.compile(
        rf"^{re.escape(output)}\s+(?:primary\s+)?connected.*?\b(\d+)x(\d+)\+",
        re.MULTILINE,
    )
    m = pattern.search(out)
    if m:
        return (int(m.group(1)), int(m.group(2)))
    return None
