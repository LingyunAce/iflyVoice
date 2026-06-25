#!/usr/bin/env python3
"""Sorted VCP compatibility report. Requires: sudo ddcutil, network to WebDDCUtil."""
import urllib.request, json, subprocess, re, sys

# ── Category mapping from VCP code ranges (VESA MCCS standard groups) ──
def vcp_category(code):
    if code == 0x00: return "Preset Operations"
    if 0x01 <= code <= 0x0A: return "Preset Operations"
    if code in (0x0B, 0x0C): return "Image Adjustment"
    if 0x0E <= code <= 0x13: return "Image Adjustment"
    if code == 0x14: return "Image Adjustment"
    if 0x16 <= code <= 0x1F: return "Image Adjustment"
    if 0x20 <= code <= 0x2E: return "Image Adjustment"
    if 0x30 <= code <= 0x3E: return "Image Adjustment"
    if 0x40 <= code <= 0x4C: return "Image Adjustment"
    if 0x52 <= code <= 0x5E: return "Image Adjustment"
    if 0x60 <= code <= 0x65: return "DDC/CI Capabilities"
    if code in (0x66,): return "Image Adjustment"
    if 0x6B <= code <= 0x7C: return "Image Adjustment"
    if code in (0x82, 0x84, 0x86, 0x87, 0x88, 0x8A, 0x8B, 0x8C, 0x8D, 0x8E, 0x8F): return "Display Controls"
    if 0x90 <= code <= 0x98: return "Display Controls"
    if 0x9A <= code <= 0xA7: return "Display Controls"
    if code in (0xAA,): return "Display Controls"
    if code in (0xAC, 0xAE): return "DDC/CI Capabilities"
    if code == 0xB0: return "Preset Operations"
    if code in (0xB2, 0xB4, 0xB5, 0xB6, 0xB7, 0xB8, 0xB9, 0xBA, 0xBB): return "DDC/CI Capabilities"
    if 0xBC <= code <= 0xBF: return "DDC/CI Capabilities"
    if code in (0xC0, 0xC2, 0xC3, 0xC4): return "DDC/CI Capabilities"
    if code in (0xC6, 0xC7, 0xC8, 0xC9): return "DDC/CI Capabilities"
    if 0xCA <= code <= 0xCE: return "Display Controls"
    if code in (0xCF, 0xD0, 0xD2, 0xD4): return "Display Controls"
    if code in (0xD6, 0xD7): return "Display Controls"
    if code in (0xDA, 0xDB, 0xDC, 0xDE, 0xDF): return "Display Controls"
    if 0xE0 <= code <= 0xFF: return "Manufacturer Specific"
    return "Other"

# ── 1. WebDDCUtil ──
url = "http://192.168.1.213:5002/api/v1/owners/1/entries"
req = urllib.request.Request(url, headers={"X-API-Key": "ddc_MyF_YWHGFhDj_h8XkenfauEtgudWGF76ge6AbYBLTbo"})
with urllib.request.urlopen(req, timeout=10) as resp:
    vesa = json.loads(resp.read())

# ── 2. Monitor capabilities ──
try:
    cap = subprocess.run(["sudo", "ddcutil", "capabilities"],
                         capture_output=True, text=True, timeout=10)
    cap_out = cap.stdout
    print(f"[DEBUG] ddcutil: rc={cap.returncode}, len={len(cap_out)}", file=sys.stderr)
except Exception as e:
    print(f"[ERROR] ddcutil failed: {e}", file=sys.stderr)
    cap_out = ""

supported_codes = set()
for line in cap_out.splitlines():
    m = re.match(r"\s*Feature:\s*([0-9A-Fa-f]+)\b", line)
    if m:
        supported_codes.add(int(m.group(1), 16))
print(f"[DEBUG] Found {len(supported_codes)} supported VCP codes", file=sys.stderr)

# ── 3. Build report ──
groups = {}
for e in vesa["entries"]:
    code = e["code"]
    cat = e.get("category_name") or vcp_category(code)
    ok = code in supported_codes
    groups.setdefault(cat, {"yes": [], "no": []})
    groups[cat]["yes" if ok else "no"].append(e)

total_yes = sum(len(g["yes"]) for g in groups.values())
total_no = sum(len(g["no"]) for g in groups.values())

print("# VCP Compatibility Report")
print(f"## Monitor: AOC Q27G10ZE (MCCS 2.2) vs VESA v2.2a ({vesa['count']} codes)")
print(f"**Supported: {total_yes} | Not Supported: {total_no} | Total: {vesa['count']}**")
print()

# ── Supported (grouped by category) ──
print("## ✅ Supported VCP Codes ({})".format(total_yes))
print("| VCP | Name | Type | Category | Description |")
print("|-----|------|------|----------|-------------|")
for cat in sorted(groups):
    items = sorted(groups[cat]["yes"], key=lambda e: e["code"])
    if not items:
        continue
    print(f"### {cat}")
    for e in items:
        desc = e.get("description", "")[:80]
        print(f"| 0x{e['code_hex']} | {e['name']} | {e['vcp_type']} | {cat} | {desc} |")
    print()

# ── Not Supported ──
print("## ❌ Not Supported VCP Codes ({})".format(total_no))
print("| VCP | Name | Type | Category | Description |")
print("|-----|------|------|----------|-------------|")
for cat in sorted(groups):
    items = sorted(groups[cat]["no"], key=lambda e: e["code"])
    if not items:
        continue
    print(f"### {cat}")
    for e in items:
        desc = e.get("description", "")[:80]
        print(f"| 0x{e['code_hex']} | {e['name']} | {e['vcp_type']} | {cat} | {desc} |")
    print()

# ── Summary ──
print("## Summary by Category")
print("| Category | Supported | Not Supported | Total |")
print("|----------|-----------|---------------|-------|")
for cat in sorted(groups):
    y = len(groups[cat]["yes"])
    n = len(groups[cat]["no"])
    print(f"| {cat} | {y} | {n} | {y+n} |")
print(f"| **Total** | **{total_yes}** | **{total_no}** | **{vesa['count']}** |")
