#!/usr/bin/env python3
"""Full scan of all 184 VESA VCP codes — find every readable code."""
import subprocess, json, urllib.request, re, sys

# Fetch VESA entries
url = 'http://192.168.1.213:5002/api/v1/owners/1/entries'
headers = {'X-API-Key': 'ddc_MyF_YWHGFhDj_h8XkenfauEtgudWGF76ge6AbYBLTbo'}
req = urllib.request.Request(url, headers=headers)
with urllib.request.urlopen(req, timeout=10) as resp:
    vesa = json.loads(resp.read())

total = len(vesa['entries'])
ok = []
print(f"Scanning {total} VCP codes...", file=sys.stderr)

for i, e in enumerate(vesa['entries']):
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
    if val_m or sl_m:
        val = val_m.group(1) if val_m else sl_m.group(1)
        max_m = re.search(r'max value\s*=\s*(\d+)', out)
        maxv = max_m.group(1) if max_m else '-'
        name_m = re.search(r'\(([^)]+)\)', out)
        name = name_m.group(1).strip() if name_m else '?'
        ok.append((code, name, val, maxv))
    if (i + 1) % 20 == 0:
        print(f"  {i+1}/{total}...", file=sys.stderr)

print(f"\n=== Results: {len(ok)} codes with readable values ===\n")
print(f"{'VCP':>5s}  {'Name':<42s} {'Val':>6s} {'Max':>6s}")
print('-' * 65)
for code, name, val, maxv in sorted(ok):
    print(f"0x{code:02X}   {name:<42s} {val:>6s} {maxv:>6s}")
