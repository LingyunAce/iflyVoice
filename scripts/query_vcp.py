#!/usr/bin/env python3
"""Query WebDDCUtil for VCP code definitions."""
import urllib.request, json

API_BASE = "http://192.168.1.213:5002"
API_KEY = "ddc_MyF_YWHGFhDj_h8XkenfauEtgudWGF76ge6AbYBLTbo"

url = f"{API_BASE}/api/v1/owners/1/entries"
req = urllib.request.Request(url, headers={"X-API-Key": API_KEY})
with urllib.request.urlopen(req) as resp:
    data = json.loads(resp.read())

print(f"Total: {data['count']} entries — {data['owner_name']} {data['owner_version']}")
print()

# Common DDC/CI VCP codes
targets = {
    2: "New Control Value",
    16: "Brightness",
    18: "Contrast",
    20: "Color Preset",
    96: "Input Source",
    98: "Audio Speaker Volume",
    141: "Audio Mute / Screen Blank",
    214: "Power Mode",
}

for e in data["entries"]:
    code = e["code"]
    if code in targets:
        print(f"VCP 0x{code:02X} ({e['name']})")
        print(f"  Type: {e['vcp_type']} | Category: {e['category_name']}")
        print(f"  Desc: {e['description'][:200]}")
        print()

# Also list all categories
print("=== Categories ===")
cats = {}
for e in data["entries"]:
    cn = e["category_name"]
    if cn not in cats:
        cats[cn] = 0
    cats[cn] += 1
for name, count in sorted(cats.items()):
    print(f"  {name}: {count} codes")
