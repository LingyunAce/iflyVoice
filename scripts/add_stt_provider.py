#!/usr/bin/env python3
"""Add iflyVoice STT wrapper as custom provider in OpenClaw config."""
import json, shutil, os

config_path = os.path.expanduser("~/.openclaw/openclaw.json")
shutil.copy(config_path, config_path + ".bak")
print(f"Backed up to {config_path}.bak")

with open(config_path) as f:
    content = f.read()

# Find "models: {" — the unquoted key
idx = content.find('\n  models: {')
if idx == -1:
    idx = content.find('\nmodels: {')
if idx == -1:
    print("ERROR: models section not found")
    exit(1)

# Find the opening brace
brace_start = content.index('{', idx)
# Count braces to find matching close
depth = 0
brace_end = brace_start
for i in range(brace_start, len(content)):
    if content[i] == '{':
        depth += 1
    elif content[i] == '}':
        depth -= 1
        if depth == 0:
            brace_end = i
            break

# Extract the models JSON block (after the brace)
# The content is { "mode": "merge", ... }
models_raw = content[brace_start:brace_end + 1]

# Parse and modify
models_data = json.loads(models_raw)
print(f"Current providers: {list(models_data.get('providers', {}).keys())}")

# Add xinference-stt provider
models_data.setdefault("providers", {})
models_data["providers"]["xinference-stt"] = {
    "baseUrl": "http://127.0.0.1:18766/v1",
    "apiKey": "sk-noop",
    "api": "openai-completions",
    "models": [
        {
            "id": "sensevoice",
            "name": "SenseVoiceSmall STT",
            "cost": {"input": 0, "output": 0},
            "contextWindow": 1000,
        }
    ],
}
print("Added xinference-stt provider")

# Rebuild config
models_str = json.dumps(models_data, indent=2)
# Increase indent to match original
models_str = "\n".join("  " + line if line.strip() else line
                       for line in models_str.split("\n"))
new_content = content[:brace_start] + models_str + content[brace_end + 1:]

with open(config_path, "w") as f:
    f.write(new_content)
print("Config updated successfully")
