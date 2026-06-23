"""DDC/CI display control via ddcutil (VESA MCCS over I2C).

Provides real hardware brightness/contrast/input control for external
monitors connected via HDMI or DisplayPort.  Requires:
- ddcutil package (apt install ddcutil)
- i2c group membership or sudo access for /dev/i2c-*

VCP codes (VESA MCCS v2.2):
  0x10  Brightness
  0x12  Contrast
  0x60  Input Source
  0xD6  Power mode
"""
from __future__ import annotations
import re
import subprocess
from typing import Optional

_DDCUTIL = "ddcutil"
_SUDO = "sudo"  # Remove once cat is in i2c group and session refreshed


def _run_ddc(*args: str, timeout: int = 5) -> tuple[int, str]:
    """Run ddcutil (with sudo). Returns (returncode, stdout)."""
    cmd = [_SUDO, _DDCUTIL] + list(args)
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return (r.returncode, r.stdout)
    except FileNotFoundError:
        return (127, "")
    except subprocess.TimeoutExpired:
        return (124, "")
    except Exception:
        return (255, "")


def is_ddc_available() -> bool:
    """Check whether ddcutil can detect a DDC/CI-capable display."""
    rc, out = _run_ddc("detect", timeout=3)
    return rc == 0 and "Display" in out and "I2C bus" in out


def _parse_getvcp(output: str, vcp_hex: str) -> int:
    """Parse 'current value = N' from ddcutil getvcp output.

    Example output:
      VCP code 0x10 (Brightness): current value =  70, max value =  100
    """
    # Match the line with the VCP code, extract current value
    pattern = rf"VCP code 0x{vcp_hex}.*?current value\s*=\s*(\d+)"
    m = re.search(pattern, output)
    if m:
        return int(m.group(1))
    return -1


def get_brightness() -> int:
    """Read current brightness (0-100) via DDC/CI VCP 0x10.
    Returns -1 on failure.
    """
    rc, out = _run_ddc("getvcp", "0x10")
    if rc != 0:
        return -1
    return _parse_getvcp(out, "10")


def set_brightness(value: int) -> bool:
    """Set brightness (0-100) via DDC/CI VCP 0x10.
    Returns whether the command succeeded.
    """
    v = max(0, min(100, int(value)))
    rc, _ = _run_ddc("setvcp", "0x10", str(v))
    return rc == 0


def get_max_brightness() -> int:
    """Read max brightness value (usually 100) via DDC/CI.
    Returns -1 on failure.
    """
    rc, out = _run_ddc("getvcp", "0x10")
    if rc != 0:
        return -1
    m = re.search(r"max value\s*=\s*(\d+)", out)
    if m:
        return int(m.group(1))
    return -1


def get_contrast() -> int:
    """Read current contrast (0-100) via DDC/CI VCP 0x12.
    Returns -1 on failure.
    """
    rc, out = _run_ddc("getvcp", "0x12")
    if rc != 0:
        return -1
    return _parse_getvcp(out, "12")


def set_contrast(value: int) -> bool:
    """Set contrast (0-100) via DDC/CI VCP 0x12.
    Returns whether the command succeeded.
    """
    v = max(0, min(100, int(value)))
    rc, _ = _run_ddc("setvcp", "0x12", str(v))
    return rc == 0


def list_input_sources() -> list[dict]:
    """List available input sources via DDC/CI capabilities (VCP 0x60).
    Returns list of {code, name} dicts.
    """
    rc, out = _run_ddc("capabilities", timeout=5)
    if rc != 0:
        return []

    sources = []
    in_feature_60 = False
    in_values = False

    for line in out.splitlines():
        # Detect "Feature: 60 (Input Source)" section
        if not in_feature_60:
            if re.match(r"\s*Feature:\s*60\b", line):
                in_feature_60 = True
            continue
        # Once in feature 60, look for "Values:" block
        if not in_values:
            if "Values:" in line:
                in_values = True
            elif re.match(r"\s*Feature:\s*\w+", line):
                break  # next feature before values = no values list
            continue
        # Inside Values block: stop on empty line or next Feature
        if line.strip() == "" or re.match(r"\s*Feature:\s*\w+", line):
            break
        # Parse "    0f: DisplayPort-1" — only hex code keys
        m = re.match(r"\s*([0-9a-fA-F]{2}):\s+(.+)", line)
        if m:
            sources.append({"code": m.group(1), "name": m.group(2).strip()})

    return sources


def get_current_input() -> Optional[str]:
    """Get current input source name via DDC/CI VCP 0x60."""
    rc, out = _run_ddc("getvcp", "0x60")
    if rc != 0:
        return None
    m = re.search(r"current value\s*=\s*([^,]+)", out)
    if not m:
        return None
    val_str = m.group(1).strip()
    # Also extract the hex code
    sl_match = re.search(r"sl=0x(\w+)", out)
    if sl_match:
        code = sl_match.group(1)
        return {"name": val_str, "code": code}
    return {"name": val_str, "code": ""}


def set_input_source(code: str) -> bool:
    """Set input source by hex code (e.g. '0f' for DisplayPort-1).
    Returns whether the command succeeded.
    """
    rc, _ = _run_ddc("setvcp", "0x60", f"0x{code}")
    return rc == 0


# ── Power ─────────────────────────────────────────────────────

def get_power_mode() -> Optional[str]:
    """Read power mode via DDC/CI VCP 0xD6."""
    rc, out = _run_ddc("getvcp", "0xD6")
    if rc != 0:
        return None
    m = re.search(r"current value\s*=\s*(\d+)", out)
    if not m:
        return None
    code = int(m.group(1))
    modes = {1: "on", 4: "off"}
    return modes.get(code, f"unknown({code})")


def set_power_mode(on: bool) -> bool:
    """Set power mode: True=on, False=off via DDC/CI VCP 0xD6."""
    val = "1" if on else "4"
    rc, _ = _run_ddc("setvcp", "0xD6", val)
    return rc == 0
