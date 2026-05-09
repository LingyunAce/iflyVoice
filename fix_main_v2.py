#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
fix_main_v2.py — 一次性修复 main.js 所有问题：
1. 删除第126-177行的孤立代码残片（initSpeechRecognition/initApiSelector/loadAudioDevices 函数体残留）
2. 删除 Ollama 配置相关的 DOM 引用和方法（ollamaHostInput/ollamaPortInput/ollamaConfigBtn/initOllamaConfig）
"""
import re

FILE = r'C:\Users\a1318\WorkBuddy\xunfei_yuyin\iflyVoice\main.js'

with open(FILE, 'r', encoding='utf-8') as f:
    lines = f.readlines()

print(f'Total lines: {len(lines)}')

# ====== Step 1: 找到孤立代码的精确行范围 ======
# 孤立代码从 "    // ═══════════════════════════════════════" (语音识别初始化注释) 开始
# 到 "    // ═══════════════════════════════════════" (绑定语音录音事件注释) 之前结束

start_orphan = None
end_orphan = None

for i, line in enumerate(lines):
    # 找孤立块开始：语音识别初始化注释（没有函数签名）
    if '    // ' in line and line.strip().startswith('//') and '语音识别初始化' in line:
        # 确认下一行不是函数声明而是直接用 this.xxx
        if i + 1 < len(lines) and 'this.recognition' in lines[i + 1]:
            start_orphan = i
            print(f'Orphan block START at line {i+1}: [{line.rstrip()}]')
    
    # 找孤立块结束：绑定语音录音事件注释
    if '绑定语音录音事件' in line:
        end_orphan = i
        print(f'Orphan block END before line {i+1}: [{line.rstrip()}]')

if start_orphan is None or end_orphan is None:
    print('ERROR: Could not find orphan block boundaries!')
    exit(1)

# ====== Step 2: 删除孤立代码 ======
orphan_lines = lines[start_orphan:end_orphan]
print(f'\nRemoving {len(orphan_lines)} orphaned lines ({start_orphan+1} to {end_orphan})')
print('--- First 3 orphan lines ---')
for l in orphan_lines[:3]:
    print(f'  {l.rstrip()}')
print('--- Last 3 orphan lines ---')
for l in orphan_lines[-3:]:
    print(f'  {l.rstrip()}')

new_lines = lines[:start_orphan] + lines[end_orphan:]
print(f'\nAfter removing orphan: {len(new_lines)} lines (was {len(lines)})')

# ====== Step 3: 删除 Ollama 配置 DOM 引用（构造函数中） ======
# 删除 this.ollamaHostInput, this.ollamaPortInput, this.ollamaConfigBtn 三行
cleaned_lines = []
removed_dom_refs = 0
for line in new_lines:
    if ('this.ollamaHostInput' in line and '=' in line) or \
       ('this.ollamaPortInput' in line and '=' in line) or \
       ('this.ollamaConfigBtn' in line and '=' in line):
        removed_dom_refs += 1
        print(f'Removed DOM ref: [{line.rstrip()}]')
        continue
    cleaned_lines.append(line)
print(f'\nRemoved {removed_dom_refs} DOM refs, now {len(cleaned_lines)} lines')

# ====== Step 4: 删除 init() 中的 initOllamaConfig 调用 ======
cleaned_lines2 = []
for line in cleaned_lines:
    if 'this.initOllamaConfig()' in line:
        print(f'Removed init call: [{line.rstrip()}]')
        continue
    cleaned_lines2.append(line)

# ====== Step 5: 删除整个 initOllamaConfig() 方法 ======
# 从 /** Ollama 服务器地址配置 */ 到该方法结束的 }
method_start = None
method_end = None
brace_depth = 0
in_method = False

for i, line in enumerate(cleaned_lines2):
    if 'Ollama' in line and '服务器地址配置' in line:
        method_start = i
        in_method = True
        brace_depth = 0
        print(f'\ninitOllamaConfig START at line {i+1}')
    
    if in_method:
        brace_depth += line.count('{') - line.count('}')
        if brace_depth > 0 and i > method_start:
            pass  # 还在方法内
        
        # 方法结束检测：回到 0 depth 且遇到了独立的 } 后面是空行或下一个方法
        if brace_depth == 0 and i > method_start and line.strip() == '}':
            method_end = i
            print(f'initOllamaConfig END at line {i+1}')
            break

if method_start is not None and method_end is not None:
    final_lines = cleaned_lines2[:method_start] + cleaned_lines2[method_end+1:]
    print(f'Removed initOllamaConfig method ({method_start+1} to {method_end+1}), now {len(final_lines)} lines')
else:
    print('WARNING: initOllamaConfig method not found, skipping')
    final_lines = cleaned_lines2

# ====== Write output ======
with open(FILE, 'w', encoding='utf-8') as f:
    f.writelines(final_lines)

print(f'\n=== DONE === Written {len(final_lines)} lines to {FILE}')

# Verify no orphaned references remain
content = ''.join(final_lines)
checks = [
    ('initSpeechRecognition', 'initSpeechRecognition'),
    ('initApiSelector', 'initApiSelector'),
    ('loadAudioDevices', 'loadAudioDevices'),
    ('ollamaHostInput', 'ollamaHostInput'),
    ('ollamaPortInput', 'ollamaPortInput'),
    ('ollamaConfigBtn', 'ollamaConfigBtn'),
    ('initOllamaConfig', 'initOllamaConfig'),
]
print('\n=== Verification ===')
for name, label in checks:
    found = content.find(name)
    status = 'CLEAN' if found == -1 else f'STILL PRESENT at pos {found}'
    print(f'  {label}: {status}')
