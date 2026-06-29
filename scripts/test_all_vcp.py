#!/usr/bin/env python3
"""Test all VCP codes from ddcutil capabilities — check readability and values."""
import subprocess, re

cap = subprocess.run(['sudo', 'ddcutil', 'capabilities'],
                     capture_output=True, text=True, timeout=10)
codes = set()
for line in cap.stdout.splitlines():
    m = re.match(r'\s*Feature:\s*([0-9A-Fa-f]+)\s', line)
    if m:
        codes.add(int(m.group(1), 16))
codes = sorted(codes)

print(f"{'VCP':>4s}  {'Name':<40s} {'Val':>6s} {'Max':>6s}  Status")
print('-' * 78)

ok_list, wo_list, err_list = [], [], []

for code in codes:
    hex_code = f'0x{code:02X}'
    result = subprocess.run(['sudo', 'ddcutil', 'getvcp', hex_code],
                            capture_output=True, text=True, timeout=5)
    out = result.stdout + result.stderr

    name_m = re.search(r'\(([^)]+)\)', out)
    name = name_m.group(1).strip() if name_m else 'unknown'
    val_m = re.search(r'current value\s*=\s*(\d+)', out)
    max_m = re.search(r'max value\s*=\s*(\d+)', out)
    sl_m = re.search(r'sl=0x(\w+)', out)
    val = val_m.group(1) if val_m else (sl_m.group(1) if sl_m else '?')
    maxv = max_m.group(1) if max_m else '-'

    if result.returncode == 0:
        if 'not readable' in out.lower():
            status = 'WO'
            wo_list.append(code)
        else:
            status = 'OK'
            ok_list.append(code)
    else:
        status = f'ERR({result.returncode})'
        err_list.append(code)

    print(f'{hex_code:>4s}  {name:<40s} {val:>6s} {maxv:>6s}  {status}')

print()
print('=== Summary ===')
print(f'Readable:   {len(ok_list)}')
print(f'Write-only: {len(wo_list)}')
print(f'Error:      {len(err_list)}')
print(f'Total:      {len(codes)}')
print()
if wo_list:
    print(f'WO codes: {[f"0x{c:02X}" for c in wo_list]}')
if err_list:
    print(f'ERR codes: {[f"0x{c:02X}" for c in err_list]}')
