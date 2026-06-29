#!/usr/bin/env python3
"""Check WebDDCUtil for changes since 2026-06-23."""
import urllib.request
import json

url = "http://192.168.1.213:5002/api/v1/owners/1/entries"
headers = {"X-API-Key": "ddc_MyF_YWHGFhDj_h8XkenfauEtgudWGF76ge6AbYBLTbo"}
req = urllib.request.Request(url, headers=headers)

with urllib.request.urlopen(req, timeout=10) as resp:
    data = json.loads(resp.read())

print(f"Owner: {data.get('owner_name', '?')} {data.get('owner_version', '?')}")
print(f"Total entries: {data['count']}")
print()

# Key VCP codes we care about
targets = {
    16: 0x10, 18: 0x12, 20: 0x14,  # Brightness, Contrast, Color
    96: 0x60, 202: 0xCA, 220: 0xDC,  # Input, OSD, DisplayApp
    214: 0xD6, 204: 0xCC,  # Power, OSD Lang
}

for e in data["entries"]:
    code = e["code"]
    if code in targets:
        # Show all keys to detect schema changes
        print(f"VCP 0x{e['code_hex']} '{e['name']}' [{e['vcp_type']}]")
        cat = e.get('category_name', e.get('category', '?'))
        print(f"  Cat: {cat}")
        print(f"  Desc: {e.get('description','')[:150]}")
        print(f"  Keys: {list(e.keys())}")
        print()

# Categories summary
cats = {}
for e in data["entries"]:
    cn = e["category_name"]
    cats[cn] = cats.get(cn, 0) + 1
print("=== Categories ===")
for name, count in sorted(cats.items()):
    print(f"  {name}: {count}")

# Check for any new categories
print()
print("=== Previously known categories ===")
known = ["Preset Operations", "Image Adjustment", "Display Controls",
         "DDC/CI Capabilities", "Manufacturer Specific"]
for k in known:
    status = "EXISTS" if k in cats else "MISSING"
    print(f"  {k}: {status}")
for name in cats:
    if name not in known:
        print(f"  NEW: {name} ({cats[name]} entries)")
