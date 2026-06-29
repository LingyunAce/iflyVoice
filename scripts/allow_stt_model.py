#!/usr/bin/env python3
"""Add xinference-stt/sensevoice to agent allowed models in OpenClaw config."""
import shutil

config_path = "/home/cat/.openclaw/openclaw.json"
shutil.copy(config_path, config_path + ".bak4")

with open(config_path) as f:
    lines = f.readlines()

# Find the FIRST "models": line (agent section, not provider section)
found_first = False
insert_at = None
depth = 0

for i, line in enumerate(lines):
    if not found_first:
        if '"models":' in line.strip():
            found_first = True
        continue
    # Inside agent models block
    if '"deepseek/deepseek-v4-pro"' in line:
        # Find end of this entry (matching brace)
        if '{' in lines[i+1]:
            d = 0
            for j in range(i+1, len(lines)):
                d += lines[j].count('{') - lines[j].count('}')
                if d == 0:
                    insert_at = j + 1
                    break
        elif '{' in line:
            # Entry on same line
            d = line.count('{') - line.count('}')
            for j in range(i+1, len(lines)):
                d += lines[j].count('{') - lines[j].count('}')
                if d == 0:
                    insert_at = j + 1
                    break
        else:
            insert_at = i + 1
        break

if insert_at:
    lines.insert(insert_at,
                 '        "xinference-stt/sensevoice": { "alias": "STT" },\n')
    with open(config_path, "w") as f:
        f.writelines(lines)
    print(f"Inserted at line {insert_at + 1}")
else:
    print("Could not find insertion point")
    # Fallback: try sed-like replacement
    with open(config_path, "w") as f:
        for line in lines:
            if '"deepseek/deepseek-v4-pro":' in line and 'Pro' in line:
                f.write(line)
                f.write('        "xinference-stt/sensevoice": { "alias": "STT" },\n')
            else:
                f.write(line)
    print("Fallback: inserted after deepseek-v4-pro line")
