#!/usr/bin/env python3
"""Cross-reference WebDDCUtil VCP codes against monitor's actual capabilities."""
import urllib.request, json, subprocess, re

# 1. Fetch WebDDCUtil VESA v2.2a entries
url = "http://192.168.1.213:5002/api/v1/owners/1/entries"
headers = {"X-API-Key": "ddc_MyF_YWHGFhDj_h8XkenfauEtgudWGF76ge6AbYBLTbo"}
req = urllib.request.Request(url, headers=headers)
with urllib.request.urlopen(req, timeout=10) as resp:
    vesa_data = json.loads(resp.read())

# 2. Parse ddcutil capabilities for supported features
cap_out = subprocess.run(
    ["sudo", "ddcutil", "capabilities"], capture_output=True, text=True, timeout=10
).stdout

supported = {}  # vcp_code_hex -> [values list or None]
in_feature = False
current_code = None
for line in cap_out.splitlines():
    fm = re.match(r"\s*Feature:\s*([0-9A-Fa-f]+)\s", line)
    if fm:
        current_code = int(fm.group(1), 16)
        supported[current_code] = None  # no listed values yet
        in_feature = True
        continue
    if in_feature and "Values:" in line:
        supported[current_code] = []
        continue
    if in_feature and supported.get(current_code) is not None and isinstance(supported[current_code], list):
        vm = re.match(r"\s*([0-9a-fA-F]+):\s+(.+)", line)
        if vm:
            supported[current_code].append({"code": vm.group(1), "name": vm.group(2).strip()})
        else:
            # End of values block
            if line.strip() == "" or re.match(r"\s*Feature:", line):
                if current_code in supported and supported[current_code] == []:
                    supported[current_code] = None  # no parsed values, flag as supported

# 3. Build report
print("# VCP Code Compatibility Report")
print(f"## Monitor: AOC Q27G10ZE (MCCS 2.2) vs VESA v2.2a ({vesa_data['count']} codes)")
print()

# Category summary
cats = {}
for e in vesa_data["entries"]:
    code = e["code"]
    hex_code = e["code_hex"]
    cat = e.get("category_name") or ""
    if cat not in cats:
        cats[cat] = {"total": 0, "supported": 0, "entries": []}
    cats[cat]["total"] += 1
    status = "YES" if code in supported else "NO"
    if code in supported:
        cats[cat]["supported"] += 1
    cats[cat]["entries"].append((code, hex_code, e["name"], status, e["vcp_type"], e["description"], supported.get(code)))

print("## Summary")
print(f"| Category | Supported / Total |")
print(f"|----------|-------------------|")
for cat in sorted(cats):
    c = cats[cat]
    print(f"| {cat} | {c['supported']} / {c['total']} |")
print()

# Detailed table
print("## All VCP Codes")
print("| VCP | Name | Type | Supported | Values |")
print("|-----|------|------|-----------|--------|")

for cat in sorted(cats):
    print(f"### {cat}")
    for code, hex_code, name, status, vcp_type, desc, vals in cats[cat]["entries"]:
        val_str = ""
        if vals and isinstance(vals, list):
            val_str = ", ".join(f"{v['code']}={v['name']}" for v in vals[:5])
            if len(vals) > 5:
                val_str += f", +{len(vals)-5} more"
        mark = "✅" if status == "YES" else "—"
        print(f"| 0x{hex_code} | {name} | {vcp_type} | {mark} | {val_str} |")
    print()
