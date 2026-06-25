#!/usr/bin/env python3
"""Full scan of 184 VESA VCP codes — find all readable on AOC Q27G10ZE."""
import subprocess, json, urllib.request, re

CN = {
    0x10: "亮度", 0x12: "对比度", 0x14: "色温预设",
    0x16: "红色增益", 0x18: "绿色增益", 0x1A: "蓝色增益",
    0x1E: "自动设置", 0x20: "水平位置", 0x30: "垂直位置",
    0x60: "输入源选择", 0x62: "扬声器音量（0=静音, 100=最大）",
    0x6C: "视频黑电平(红)", 0x6E: "视频黑电平(绿)", 0x70: "视频黑电平(蓝)",
    0x86: "缩放模式", 0x87: "锐度", 0x8D: "静音/息屏",
    0xB2: "子像素布局", 0xB6: "面板技术类型", 0xC0: "累计使用时间",
    0xC8: "显示控制器ID", 0xCA: "OSD/按键控制", 0xCC: "OSD语言",
    0xD6: "电源模式", 0xDC: "显示场景模式",
    0xE2: "厂商自定义 E2", 0xE6: "厂商自定义 E6",
    0xED: "厂商自定义 ED", 0xF8: "厂商自定义 F8",
}

# Read-only codes (from VESA spec)
RO_CODES = {0x1E, 0xB2, 0xB6, 0xC0, 0xC8}

# Fetch VESA entries
url = 'http://192.168.1.213:5002/api/v1/owners/1/entries'
headers = {'X-API-Key': 'ddc_MyF_YWHGFhDj_h8XkenfauEtgudWGF76ge6AbYBLTbo'}
req = urllib.request.Request(url, headers=headers)
with urllib.request.urlopen(req, timeout=10) as resp:
    vesa = json.loads(resp.read())

# Scan all codes
working = []
for e in vesa['entries']:
    code = e['code']
    hex_c = f'0x{code:02X}'
    result = subprocess.run(['sudo', 'ddcutil', 'getvcp', hex_c],
                            capture_output=True, text=True, timeout=3)
    out = result.stdout + result.stderr
    if result.returncode != 0:
        continue
    if 'not readable' in out.lower():
        continue
    val_m = re.search(r'current value\s*=\s*(\d+)', out)
    sl_m = re.search(r'sl=0x(\w+)', out)
    level_m = re.search(r'(?:Volume level|level):\s*(\d+)', out, re.IGNORECASE)
    if not val_m and not sl_m and not level_m:
        continue
    if val_m: val = val_m.group(1)
    elif sl_m: val = sl_m.group(1)
    else: val = level_m.group(1)
    max_m = re.search(r'max value\s*=\s*(\d+)', out)
    maxv = max_m.group(1) if max_m else '--'

    vtype = 'ro' if code in RO_CODES else 'rw'
    cn = CN.get(code, '')

    # MCP command
    if code == 0x10:
        mcp = 'iflyvoice__set_brightness {"value": N}'
    elif code == 0x12:
        mcp = 'iflyvoice__set_contrast {"value": N}'
    elif code == 0x14:
        mcp = 'iflyvoice__set_color_temp {"preset": "6500 K"}'
    elif code in (0x16, 0x18, 0x1A):
        mcp = 'iflyvoice__set_rgb_gain {"red":N,"green":N,"blue":N}'
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
    elif vtype == 'ro':
        mcp = f'iflyvoice__vcp_read {{"code": "{code:02X}"}}'
    else:
        mcp = f'iflyvoice__vcp_write {{"code": "{code:02X}", "value": N}}'

    name_m = re.search(r'\(([^)]+)\)', out)
    name = name_m.group(1).strip() if name_m else e.get('name', '?')
    working.append((code, name, cn, val, maxv, vtype, mcp))

# Print markdown
print("| VCP | 功能 | 中文 | 当前值 | 最大 | 类型 | OpenClaw MCP 命令 |")
print("|-----|------|------|--------|------|------|-------------------|")
for code, name, cn, val, maxv, vtype, mcp in sorted(working):
    print(f"| `0x{code:02X}` | {name} | {cn} | {val} | {maxv} | {vtype} | `{mcp}` |")

print()
print(f"**全量扫描 184 个 VCP 码，{len(working)} 个可读可用**")
