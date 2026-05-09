import re

with open(r'C:\Users\a1318\WorkBuddy\xunfei_yuyin\iflyVoice\main.js', 'r', encoding='utf-8') as f:
    lines = f.readlines()

# --- Step 1: find start/end lines of 3 methods ---
def find_method_end(start_idx):
    """Track brace level from start_idx, return end line index (the '    }' line)"""
    brace_level = 0
    started = False
    for i in range(start_idx, len(lines)):
        line = lines[i]
        # Remove string literals to avoid counting braces inside strings
        # Simple approach: remove single-quoted and double-quoted strings
        stripped = line
        # Remove single-quote strings
        stripped = re.sub(r"'[^']*'", ' ', stripped)
        # Remove double-quote strings
        stripped = re.sub(r'"[^"]*"', ' ', stripped)
        # Remove template literals (backtick strings)
        stripped = re.sub(r'`[^`]*`', ' ', stripped)

        open_c = stripped.count('{')
        close_c = stripped.count('}')

        if open_c > 0:
            started = True
        brace_level += open_c - close_c

        if started and brace_level <= 0:
            return i  # line index of the closing '    }'
    return len(lines) - 1

# Find start lines
starts = {}
for i, line in enumerate(lines):
    s = line.strip()
    if s.startswith('initSpeechRecognition('):
        starts['initSpeechRecognition'] = i
    elif s.startswith('initApiSelector('):
        starts['initApiSelector'] = i
    elif s.startswith('async loadAudioDevices('):
        starts['loadAudioDevices'] = i

print("Start lines (0-indexed):")
for name, idx in starts.items():
    print(f"  {name}: line {idx+1}")

# Find end lines
ends = {}
for name, start in starts.items():
    end = find_method_end(start + 1)  # start from body
    ends[name] = end
    print(f"  {name} end: line {end+1} => {lines[end].rstrip()}")

# --- Step 2: remove those lines ---
skip = set()
for name, start in starts.items():
    end = ends[name]
    for i in range(start, end + 1):
        skip.add(i)
    # Also skip the comment block before each method
    # Look backwards from start to find the comment lines
    i = start - 1
    while i >= 0 and (lines[i].strip().startswith('//') or lines[i].strip() == ''):
        skip.add(i)
        i -= 1

keep = [lines[i] for i in range(len(lines)) if i not in skip]

print(f"\nAfter removing 3 methods: {len(keep)} lines (was {len(lines)})")

# --- Step 3: simplify startRecording() and stopRecording() ---
content = ''.join(keep)

# Simplify startRecording: remove 'browser' and 'iflytek' branches
# Replace the whole method body from 'async startRecording() {' to its '    }'
# Actually, let's rewrite startRecording and stopRecording entirely

# For startRecording: keep only the 'sensevoice' branch logic
# Find startRecording start
sr_start = content.find('    async startRecording() {')
if sr_start != -1:
    # Find the end of startRecording
    sr_end = sr_start
    brace = 0
    started = False
    for i in range(sr_start, len(content)):
        ch = content[i]
        if ch == '{':
            brace += 1
            started = True
        if ch == '}':
            brace -= 1
            if started and brace <= 0:
                sr_end = i
                break
    # Now we have startRecording from sr_start to sr_end
    # Replace with simplified version
    new_sr = '''    async startRecording() {
        if (this.isRecording) return;
        this.recognizedText = '';
        this.displayResult('', true);
        this.updateSendBtn();

        try {
            // SenseVoice：通过 MediaRecorder 录音，结束后上传到服务器
            if (!window.SenseVoiceClient) { this.addDebugLog('SenseVoice 模块未加载'); return; }
            this.audioChunks = [];
            const stream = await navigator.mediaDevices.getUserMedia({ audio: true, video: false });
            const types = ['audio/webm;codecs=opus', 'audio/webm', 'audio/ogg'];
            const mimeType = types.find(t => MediaRecorder.isTypeSupported(t)) || '';
            this.mediaRecorder = new MediaRecorder(stream, mimeType ? { mimeType } : {});
            this.mediaRecorder.ondataavailable = (e) => {
                if (e.data && e.data.size > 0) this.audioChunks.push(e.data);
            };
            this.mediaRecorder.onerror = (e) => {
                this.addDebugLog(`SenseVoice 录音异常: ${e.error}`);
            };
            this.mediaRecorder.start();
            this.addDebugLog('SenseVoice 正在录音...');

            this.isRecording = true;
            this.updateUI();
            this.updateStatus('正在录音...', true);
            this.recordTimer = setTimeout(() => {
                if (this.isRecording) { this.stopRecording(); this.addDebugLog('30秒自动停止'); }
            }, this.maxRecordTime);

        } catch (err) {
            this.addDebugLog(`启动录音失败: ${err.message}`);
            this.resultEl.innerHTML = `<div class="error">${err.message}</div>`;
        }
    }
'''
    content = content[:sr_start] + new_sr + content[sr_end+1:]

# Find and simplify stopRecording
sr2_start = content.find('    async stopRecording() {')
if sr2_start != -1:
    sr2_end = sr2_start
    brace = 0
    started = False
    for i in range(sr2_start, len(content)):
        ch = content[i]
        if ch == '{':
            brace += 1
            started = True
        if ch == '}':
            brace -= 1
            if started and brace <= 0:
                sr2_end = i
                break
    new_sr2 = '''    async stopRecording() {
        if (!this.isRecording) return;
        this.addDebugLog('停止录音...');
        if (this.recordTimer) { clearTimeout(this.recordTimer); this.recordTimer = null; }

        // SenseVoice: 停止录音并识别
        if (this.mediaRecorder) {
            this.mediaRecorder.stop();
            this.mediaRecorder.stream.getTracks().forEach(t => t.stop());
            await new Promise(resolve => setTimeout(resolve, 300));
            if (this.audioChunks.length === 0) {
                this.addDebugLog('SenseVoice: 无音频数据');
            } else {
                const audioBlob = new Blob(this.audioChunks, { type: this.audioChunks[0].type || 'audio/webm' });
                this.addDebugLog('SenseVoice 正在识别...');
                try {
                    const sv = new window.SenseVoiceClient();
                    const result = await sv.transcribe(audioBlob);
                    if (result.success) {
                        this.recognizedText = result.text || '';
                        this.displayResult(this.recognizedText);
                        this.updateSendBtn();
                        this.addDebugLog(`SenseVoice 识别: ${this.recognizedText}`);
                    } else {
                        this.addDebugLog(`SenseVoice 识别失败: ${result.error}`);
                    }
                } catch (e) {
                    this.addDebugLog(`SenseVoice 请求异常: ${e.message}`);
                }
            }
            this.mediaRecorder = null;
        }

        this.isRecording = false;
        this.updateUI();
        this.updateStatus('准备就绪');
        this.updateSendBtn();
    }
'''
    content = content[:sr2_start] + new_sr2 + content[sr2_end+1:]

# --- Step 4: remove handleSpeechError method ---
heid = content.find('    handleSpeechError(')
if heid != -1:
    # Find the end of handleSpeechError
    he_end = heid
    brace = 0
    started = False
    for i in range(heid, len(content)):
        ch = content[i]
        if ch == '{':
            brace += 1
            started = True
        if ch == '}':
            brace -= 1
            if started and brace <= 0:
                he_end = i
                break
    # Also remove the comment line before handleSpeechError
    # Find the line start of handleSpeechError
    line_start = content.rfind('\n', 0, heid) + 1
    # Check if there's a comment before it
    prev_nl = content.rfind('\n', 0, line_start - 1)
    comment_start = prev_nl + 1
    comment_line = content[comment_start:line_start]
    if '//' in comment_line:
        content = content[:comment_start] + content[he_end+1:]
    else:
        content = content[:line_start] + content[he_end+1:]

print("Simplified startRecording/stopRecording, removed handleSpeechError")

# Write back
with open(r'C:\Users\a1318\WorkBuddy\xunfei_yuyin\iflyVoice\main.js', 'w', encoding='utf-8') as f:
    f.write(content)

print("DONE - main.js updated successfully")
print(f"Final length: {len(content)} chars, {content.count(chr(10))} lines")
