#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
fix_v3.py — 用 ASCII 标记定位并修复 main.js
问题：第126-178行有孤立代码残片，导致整个JS无法解析
"""
import re

FILE = r'C:\Users\a1318\WorkBuddy\xunfei_yuyin\iflyVoice\main.js'

with open(FILE, 'r', encoding='utf-8') as f:
    content = f.read()
lines = content.split('\n')
print(f'Total lines: {len(lines)}')

# Strategy: find exact line numbers by ASCII-only patterns
start_line = None
end_line = None

for i, line in enumerate(lines):
    # Orphan block starts right after the empty comment section (line ~126)
    # Look for "this.recognition = new SR();" which ONLY appears in orphan code
    if 'this.recognition = new SR()' in line:
        start_line = i
        # Go back to find the comment section start (the ═ line)
        for back in range(i, max(i - 5, -1), -1):
            if '//' in lines[back] and all(c in '═ \n' for c in lines[back].strip().lstrip('/ ')):
                start_line = back
                break
        print(f'Orphan START: line {start_line + 1} (found SR ref at {i + 1})')

for i, line in enumerate(lines):
    # Orphan block ends right before bindSpeechEvents() 
    if line.strip() == 'bindSpeechEvents() {' and i > (start_line or 0):
        # Go back to the comment section start
        for back in range(i, max(i - 5, -1), -1):
            stripped = lines[back].strip()
            if stripped.startswith('//') and len(stripped) > 10 and all(c in '═ /' for c in stripped.replace(' ', '')):
                end_line = back
                break
        if end_line is None:
            end_line = i
        print(f'Orphan END: line {end_line} (before bindSpeechEvents at {i + 1})')
        break

if start_line is None or end_line is None:
    print('ERROR finding boundaries. Dumping lines 120-185:')
    for i in range(min(120, len(lines)), min(185, len(lines))):
        marker = ' >>>' if 'recognition' in lines[i] or 'bindSpeechEvents' in lines[i] else ''
        print(f'  {i+1:4d}: [{lines[i][:80]}]{marker}')
    exit(1)

# Remove orphan block
print(f'\nRemoving lines {start_line + 1} to {end_line} ({end_line - start_line} lines)')
new_lines = lines[:start_line] + lines[end_line:]

# Also remove Ollama config DOM refs
final_lines = []
removed = []
for line in new_lines:
    s = line.strip()
    # Remove DOM refs for ollama config inputs/button
    if ('this.ollamaHostInput' in line and '=' in s) or \
       ('this.ollamaPortInput' in line and '=' in s) or \
       ('this.ollamaConfigBtn' in line and '=' in s):
        removed.append(f'line: {s[:60]}')
        continue
    # Remove initOllamaConfig call
    if 'this.initOllamaConfig()' in s:
        removed.append(f'call: {s[:60]}')
        continue
    final_lines.append(line)

print(f'Removed {len(removed)} ollama-config references')
for r in removed:
    print(f'  - {r}')

# Remove initOllamaConfig method entirely
content2 = '\n'.join(final_lines)
# Find and remove initOllamaConfig method
pattern = r'\n(\s*//\s*\S.*?config.*?\n)\s*initOllamaConfig\(\)\s*\{[^}]*\}\s*\n'
m = re.search(pattern, content2)
if m:
    print(f'\nRemoved initOllamaConfig method ({len(m.group(0))} chars)')
    content2 = content2[:m.start()] + '\n' + content2[m.end():]
else:
    print('\ninitOllamaConfig method not found via regex, trying line-based...')

# Write result
with open(FILE, 'w', encoding='utf-8') as f:
    f.write(content2)

result_lines = content2.count('\n') + 1
print(f'\nDONE: Written {result_lines} lines')

# Verification
checks = [
    ('this.recognition = new SR()', 'orphan SR code'),
    ('this.apiSelector', 'apiSelector'),
    ('this.iflytekRecognizer', 'iflytekRecognizer'),
    ('initSpeechRecognition', 'initSpeechRecognition'),
    ('initApiSelector', 'initApiSelector'),
    ('loadAudioDevices', 'loadAudioDevices'),
    ('this.ollamaHostInput', 'ollamaHostInput'),
    ('this.ollamaPortInput', 'ollamaPortInput'),
    ('this.ollamaConfigBtn', 'ollamaConfigBtn'),
    ('initOllamaConfig', 'initOllamaConfig'),
]
print('\nVerification:')
all_clean = True
for pattern_str, label in checks:
    found = content2.find(pattern_str)
    status = 'OK' if found == -1 else f'FAIL at pos {found}'
    if found != -1:
        all_clean = False
    print(f'  [{status}] {label}')
print(f'\nOverall: {"ALL CLEAN" if all_clean else "ISSUES REMAINING"}')
