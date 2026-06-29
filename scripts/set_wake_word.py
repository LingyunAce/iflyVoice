#!/usr/bin/env python3
import json, sys
word = sys.argv[1] if len(sys.argv) > 1 else "小助手"
path = "/home/cat/iflyVoice/settings.json"
with open(path) as f:
    s = json.load(f)
s["wake_word"] = word
with open(path, "w") as f:
    json.dump(s, f, indent=2, ensure_ascii=False)
print(f"Wake word set to: {word}")
