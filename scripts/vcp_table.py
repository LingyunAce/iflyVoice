#!/usr/bin/env python3
"""Generate VCP code table with MCP commands for OpenClaw."""
import subprocess, re

cap = subprocess.run(["sudo", "ddcutil", "capabilities"],
                     capture_output=True, text=True, timeout=10).stdout
all_codes = set()
for line in cap.splitlines():
    m = re.match(r'\s*Feature:\s*([0-9A-Fa-f]+)\s', line)
    if m:
        all_codes.add(int(m.group(1), 16))

working = []
for code in sorted(all_codes):
    hex_code = f'0x{code:02X}'
    result = subprocess.run(["sudo", "ddcutil", "getvcp", hex_code],
                            capture_output=True, text=True, timeout=5)
    out = result.stdout + result.stderr
    if result.returncode != 0:
        continue
    if "not readable" in out.lower():
        continue

    name_m = re.search(r'\(([^)]+)\)', out)
    name = name_m.group(1).strip() if name_m else "?"
    val_m = re.search(r'current value\s*=\s*(\d+)', out)
    max_m = re.search(r'max value\s*=\s*(\d+)', out)
    sl_m = re.search(r'sl=0x(\w+)', out)
    val = val_m.group(1) if val_m else (sl_m.group(1) if sl_m else "--")
    maxv = max_m.group(1) if max_m else "--"

    # Determine vcp_type
    if code in (0x04, 0x05, 0x08):
        vtype = "wo"
    elif code in (0x02, 0x0C, 0x52, 0xAC, 0xAE, 0xB2, 0xB6, 0xC6, 0xC8, 0xC9, 0xDF):
        vtype = "ro"
    else:
        vtype = "rw"

    # MCP command
    if code == 0x10:
        mcp = 'iflyvoice__set_brightness {"value": N}'
    elif code == 0x12:
        mcp = 'iflyvoice__set_contrast {"value": N}'
    elif code == 0x14:
        mcp = 'iflyvoice__set_color_temp {"preset": "6500 K"}'
    elif code in (0x16, 0x18, 0x1A):
        mcp = 'iflyvoice__set_rgb_gain {"red":50,"green":50,"blue":50}'
    elif code == 0x60:
        mcp = 'iflyvoice__set_input {"code": "0f"}  # 0f=DP-1, 11=HDMI-1'
    elif code == 0xD6:
        mcp = 'iflyvoice__vcp_write {"code": "D6", "value": 1}  # 1=on, 4=off'
    elif code == 0xCA:
        mcp = 'iflyvoice__osd_control {"action": "lock"}  # lock/unlock/read'
    elif code == 0xCC:
        mcp = 'iflyvoice__osd_control {"action": "set_lang", "code": 2}  # 2=EN, 0x0d=CN'
    elif code == 0x62:
        mcp = 'iflyvoice__display_config {"what": "volume", "value": N}'
    elif code == 0x86:
        mcp = 'iflyvoice__display_config {"what": "scaling", "value": N}  # 1=1:1, 2=full'
    elif code == 0x8D:
        mcp = 'iflyvoice__display_config {"what": "mute", "mute": true}'
    elif code == 0xDC:
        mcp = 'iflyvoice__display_config {"what": "mode", "value": N}'
    elif vtype == "ro":
        mcp = f'iflyvoice__vcp_read {{"code": "{code:02X}"}}'
    else:
        mcp = f'iflyvoice__vcp_write {{"code": "{code:02X}", "value": N}}'

    working.append((code, name, val, maxv, vtype, mcp))

# Print markdown table
print("| VCP | 功能 | 当前值 | 最大 | 类型 | OpenClaw MCP 命令 |")
print("|-----|------|--------|------|------|-------------------|")
for code, name, val, maxv, vtype, mcp in working:
    code_str = f"`0x{code:02X}`"
    print(f"| {code_str} | {name} | {val} | {maxv} | {vtype} | `{mcp}` |")

print()
print(f"**共 {len(working)} 个可用 VCP 码**")
