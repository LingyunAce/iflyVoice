/**
 * main.js — 语音 AI 助手主控制器
 * 负责：语音识别（浏览器 / 讯飞）+ Ollama 对话 + UI 联动
 */
class SpeechAIApp {
    constructor() {
        // ── 语音识别相关 ──
        this.recognition = null;
        this.iflytekRecognizer = null;
        this.isRecording = false;
        this.recognizedText = '';
        this.currentApi = 'browser';
        this.debugLogs = [];
        this.recordTimer = null;
        this.maxRecordTime = 30000;
        this.selectedDeviceId = null;

        // ── DOM 元素 ──
        this.recordBtn       = document.getElementById('recordBtn');
        this.statusEl        = document.getElementById('status');
        this.resultEl        = document.getElementById('result');
        this.debugLogEl      = document.getElementById('debugLog');
        this.apiSelector     = document.querySelectorAll('input[name="apiType"]');
        this.iflytekConfigDiv= document.getElementById('iflytekConfig');
        this.sendToAiBtn     = document.getElementById('sendToAiBtn');
        this.chatMessages    = document.getElementById('chatMessages');
        this.chatInput       = document.getElementById('chatInput');
        this.chatSendBtn     = document.getElementById('chatSendBtn');
        this.stopGenBtn      = document.getElementById('stopGenBtn');
        this.aiStatusEl      = document.getElementById('aiStatus');
        this.modelSelector   = document.getElementById('modelSelector');
        this.clearChatBtn    = document.getElementById('clearChatBtn');
        this.deviceSelectorEl= null; // 动态创建

        // ── Ollama 客户端 ──
        this.ollama = null;

        this.init();
    }

    // ═══════════════════════════════════════
    //  初始化
    // ═══════════════════════════════════════
    async init() {
        this.initSpeechRecognition();
        this.initApiSelector();
        this.bindSpeechEvents();
        this.bindChatEvents();
        this.loadAudioDevices();
        await this.initOllama();
    }

    // ── 初始化 Ollama 客户端 ──
    async initOllama() {
        // 先填充模型列表
        try {
            const models = await OllamaClient.fetchModels();
            if (models.length > 0) {
                this.modelSelector.innerHTML = '';
                models.forEach(m => {
                    const opt = document.createElement('option');
                    opt.value = m;
                    opt.textContent = m;
                    if (m === 'qwen3:4b') opt.selected = true;
                    this.modelSelector.appendChild(opt);
                });
                this.addDebugLog(`Ollama 已连接，可用模型: ${models.join(', ')}`);
            } else {
                this.addDebugLog('⚠ Ollama 未响应或无可用模型，请确认服务已启动');
                this.setAiStatus('⚠ Ollama 未连接');
            }
        } catch (e) {
            this.addDebugLog(`Ollama 连接失败: ${e.message}`);
            this.setAiStatus('⚠ Ollama 未连接');
        }

        this.createOllamaClient();

        // 模型切换时重建客户端（保留对话历史选项可选）
        this.modelSelector.addEventListener('change', () => {
            this.createOllamaClient();
            this.addDebugLog(`切换模型: ${this.modelSelector.value}`);
        });
    }

    createOllamaClient() {
        // 如果上一个正在生成，先中断
        if (this.ollama) this.ollama.abort();

        this.ollama = new OllamaClient({
            model: this.modelSelector.value || 'qwen3:4b',
            onToken: (token, full) => {
                this.updateStreamingBubble(full);
            },
            onDone: (clean, raw) => {
                this.finalizeAssistantBubble(clean);
                this.setGenerating(false);
            },
            onError: (err) => {
                this.appendErrorBubble(`AI 回答失败: ${err.message}`);
                this.setGenerating(false);
            },
        });
    }

    // ═══════════════════════════════════════
    //  语音识别初始化
    // ═══════════════════════════════════════
    initSpeechRecognition() {
        const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
        if (!SR) {
            this.addDebugLog('错误: 浏览器不支持 SpeechRecognition API');
            return;
        }

        this.recognition = new SR();
        this.recognition.continuous = true;
        this.recognition.interimResults = true;
        this.recognition.lang = 'zh-CN';
        this.recognition.maxAlternatives = 1;

        this.recognition.onstart  = () => { this.isRecording = true; this.updateUI(); this.updateStatus('正在录音...', true); this.addDebugLog('语音识别启动'); };
        this.recognition.onend    = () => { this.isRecording = false; this.updateUI(); this.updateStatus('准备就绪'); if (this.recordTimer) { clearTimeout(this.recordTimer); this.recordTimer = null; } };
        this.recognition.onerror  = (e) => { this.addDebugLog(`识别错误: ${e.error}`); this.handleSpeechError(e.error); };
        this.recognition.onnomatch= () => { this.addDebugLog('未匹配到语音'); };

        this.recognition.onresult = (event) => {
            let finalText = '';
            for (let i = 0; i < event.results.length; i++) finalText += event.results[i][0].transcript;
            this.recognizedText = finalText;
            this.displayResult(finalText);
            const isFinal = event.results[event.results.length - 1].isFinal;
            if (isFinal) this.addDebugLog(`最终识别: ${finalText}`);
            this.updateSendBtn();
        };

        this.addDebugLog('浏览器语音识别初始化成功');
    }

    // ── API 类型切换 ──
    initApiSelector() {
        this.apiSelector.forEach(radio => {
            radio.addEventListener('change', (e) => {
                this.currentApi = e.target.value;
                this.iflytekConfigDiv.style.display = this.currentApi === 'iflytek' ? 'block' : 'none';
                this.addDebugLog(`切换到 ${this.currentApi === 'iflytek' ? '讯飞' : '浏览器内置'} API`);
            });
        });
    }

    // ── 枚举麦克风设备（动态注入 DOM） ──
    async loadAudioDevices() {
        if (!this.deviceSelectorEl) {
            const wrapper = document.createElement('div');
            wrapper.style.cssText = 'margin:0; display:flex; flex-direction:column; gap:6px;';

            const label = document.createElement('label');
            label.textContent = '🎤 麦克风设备：';
            label.style.cssText = 'font-size:12px; font-weight:600; color:rgba(255,255,255,0.6);';

            const select = document.createElement('select');
            select.id = 'deviceSelector';
            select.style.cssText = 'padding:7px 10px; border-radius:8px; border:1px solid rgba(255,255,255,0.15); background:rgba(255,255,255,0.08); color:#fff; font-size:12px; cursor:pointer; outline:none;';

            const hint = document.createElement('p');
            hint.style.cssText = 'font-size:11px; color:rgba(255,255,255,0.35); margin:0;';
            hint.textContent = '若走 Realtek 通道，请选择耳机/蓝牙对应条目';

            wrapper.appendChild(label);
            wrapper.appendChild(select);
            wrapper.appendChild(hint);
            this.iflytekConfigDiv.appendChild(wrapper);
            this.deviceSelectorEl = select;
        }

        try {
            const devices = await enumerateAudioInputDevices();
            this.deviceSelectorEl.innerHTML = '<option value="">默认麦克风</option>';
            devices.forEach(d => {
                const opt = document.createElement('option');
                opt.value = d.deviceId;
                opt.textContent = d.label;
                this.deviceSelectorEl.appendChild(opt);
            });
            this.addDebugLog(`找到 ${devices.length} 个音频输入设备`);
            this.deviceSelectorEl.addEventListener('change', (e) => {
                this.selectedDeviceId = e.target.value || null;
                this.addDebugLog(`切换麦克风: ${e.target.options[e.target.selectedIndex].text}`);
            });
        } catch (err) {
            this.addDebugLog(`枚举设备失败: ${err.message}`);
        }
    }

    // ═══════════════════════════════════════
    //  绑定语音录音事件
    // ═══════════════════════════════════════
    bindSpeechEvents() {
        this.recordBtn.addEventListener('click', () => this.handleRecordClick());
        this.sendToAiBtn.addEventListener('click', () => {
            const text = this.recognizedText.trim();
            if (text) this.sendToOllama(text);
        });
    }

    async handleRecordClick() {
        this.isRecording ? await this.stopRecording() : await this.startRecording();
    }

    async startRecording() {
        if (this.isRecording) return;
        this.recognizedText = '';
        this.displayResult('', true); // 清空+placeholder
        this.updateSendBtn();

        try {
            if (this.currentApi === 'browser') {
                if (!this.recognition) { this.addDebugLog('浏览器不支持语音识别'); return; }
                this.recognition.start();

            } else if (this.currentApi === 'iflytek') {
                if (!window.IflytekSpeechRecognizer) { this.addDebugLog('讯飞API模块未加载'); return; }
                this.iflytekRecognizer = new window.IflytekSpeechRecognizer({
                    appId: IFLYTEK_CONFIG.APPID,
                    apiKey: IFLYTEK_CONFIG.APIKey,
                    apiSecret: IFLYTEK_CONFIG.APISecret,
                    deviceId: this.selectedDeviceId,
                    onResult: (result) => {
                        this.recognizedText = result.text;
                        this.displayResult(result.text);
                        this.updateSendBtn();
                        this.addDebugLog(`讯飞识别: ${result.text} ${result.isFinal ? '(最终)' : '(临时)'}`);
                    },
                    onError: (err) => {
                        this.addDebugLog(`讯飞错误: ${err.message}`);
                        this.resultEl.innerHTML = `<div class="error">${err.message}</div>`;
                    },
                    onStatusChange: (s) => this.addDebugLog(`讯飞状态: ${s}`),
                });
                this.iflytekRecognizer.addDebugLog = (msg) => this.addDebugLog(`[讯飞] ${msg}`);
                await this.iflytekRecognizer.start();
            }

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

    async stopRecording() {
        if (!this.isRecording) return;
        this.addDebugLog('停止录音...');
        if (this.recordTimer) { clearTimeout(this.recordTimer); this.recordTimer = null; }

        if (this.currentApi === 'browser' && this.recognition) {
            if (this.recognizedText.trim()) this.displayResult(this.recognizedText);
            this.recognition.stop();

        } else if (this.currentApi === 'iflytek' && this.iflytekRecognizer) {
            this.iflytekRecognizer.stop();
            this.addDebugLog('等待讯飞最终结果...');
            if (this.recognizedText.trim()) this.displayResult(this.recognizedText);
            this.iflytekRecognizer = null;
        }

        this.isRecording = false;
        this.updateUI();
        this.updateStatus('准备就绪');
        this.updateSendBtn();
    }

    // ═══════════════════════════════════════
    //  绑定 AI 对话事件
    // ═══════════════════════════════════════
    bindChatEvents() {
        // 发送按钮
        this.chatSendBtn.addEventListener('click', () => this.handleChatSend());

        // Enter 发送（Shift+Enter 换行）
        this.chatInput.addEventListener('keydown', (e) => {
            if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); this.handleChatSend(); }
        });

        // 停止生成
        this.stopGenBtn.addEventListener('click', () => {
            if (this.ollama) this.ollama.abort();
            this.setGenerating(false);
            this.finalizeAssistantBubble(this._streamingText || '（已中断）');
            this.addDebugLog('用户中断生成');
        });

        // 清空对话
        this.clearChatBtn.addEventListener('click', () => {
            if (this.ollama) { this.ollama.abort(); this.ollama.clearHistory(); }
            this.chatMessages.innerHTML = `
                <div class="chat-welcome">
                    <div class="welcome-icon">&#129504;</div>
                    <p>对话已清空，重新开始</p>
                </div>`;
            this.setGenerating(false);
            this.addDebugLog('对话历史已清空');
        });
    }

    handleChatSend() {
        const text = this.chatInput.value.trim();
        if (!text || this.ollama?.isGenerating) return;
        this.chatInput.value = '';
        this.sendToOllama(text);
    }

    // ═══════════════════════════════════════
    //  发送消息给 Ollama
    // ═══════════════════════════════════════
    async sendToOllama(text) {
        if (!this.ollama) { this.appendErrorBubble('Ollama 客户端未初始化'); return; }
        if (this.ollama.isGenerating) { this.addDebugLog('上一条回答还在生成中，请稍候'); return; }

        // 移除欢迎语
        const welcome = this.chatMessages.querySelector('.chat-welcome');
        if (welcome) welcome.remove();

        // 显示用户气泡
        this.appendUserBubble(text);
        this.addDebugLog(`发送给 Ollama: ${text}`);

        // 创建 AI 气泡（思考中）
        this._streamingText = '';
        this._streamingBubbleEl = this.appendAssistantBubble();

        this.setGenerating(true);
        this.setAiStatus(`${this.ollama.model} 正在思考...`);

        try {
            await this.ollama.chat(text);
        } catch (e) {
            // 错误已由 onError 回调处理
        }
    }

    // ═══════════════════════════════════════
    //  对话 UI 辅助方法
    // ═══════════════════════════════════════
    appendUserBubble(text) {
        const el = document.createElement('div');
        el.className = 'message user';
        el.innerHTML = `
            <div class="message-avatar">&#128100;</div>
            <div class="message-bubble">${escapeHtml(text)}</div>`;
        this.chatMessages.appendChild(el);
        this.scrollToBottom();
        return el;
    }

    appendAssistantBubble() {
        const el = document.createElement('div');
        el.className = 'message assistant';
        el.innerHTML = `
            <div class="message-avatar">&#129504;</div>
            <div class="message-bubble">
                <div class="thinking-dots"><span></span><span></span><span></span></div>
            </div>`;
        this.chatMessages.appendChild(el);
        this.scrollToBottom();
        return el.querySelector('.message-bubble');
    }

    updateStreamingBubble(fullText) {
        this._streamingText = fullText;
        if (!this._streamingBubbleEl) return;

        // 过滤掉 <think>...</think> 块，保留其余内容实时显示
        const visible = fullText.replace(/<think>[\s\S]*?<\/think>/g, '').replace(/<think>[\s\S]*/g, '');
        this._streamingBubbleEl.innerHTML = markdownToHtml(visible) + '<span class="typing-cursor"></span>';
        this.scrollToBottom();
    }

    finalizeAssistantBubble(cleanText) {
        if (!this._streamingBubbleEl) return;
        this._streamingBubbleEl.innerHTML = markdownToHtml(cleanText) || '（无内容）';
        this._streamingBubbleEl = null;
        this._streamingText = '';
        this.setAiStatus('');
        this.scrollToBottom();
        this.addDebugLog(`AI 回答完成 (${cleanText.length} 字)`);
    }

    appendErrorBubble(msg) {
        const el = document.createElement('div');
        el.className = 'message assistant';
        el.innerHTML = `
            <div class="message-avatar">&#129504;</div>
            <div class="message-bubble" style="color:#ff6b7a; border-color:rgba(255,71,87,0.3);">⚠ ${escapeHtml(msg)}</div>`;
        this.chatMessages.appendChild(el);
        this.scrollToBottom();
    }

    setGenerating(val) {
        this.chatSendBtn.disabled = val;
        this.stopGenBtn.style.display = val ? 'inline-block' : 'none';
        if (!val) this.setAiStatus('');
    }

    setAiStatus(text) {
        if (this.aiStatusEl) this.aiStatusEl.textContent = text;
    }

    scrollToBottom() {
        this.chatMessages.scrollTop = this.chatMessages.scrollHeight;
    }

    // ═══════════════════════════════════════
    //  语音 UI 辅助方法
    // ═══════════════════════════════════════
    displayResult(text, clear = false) {
        if (clear || !text) {
            this.resultEl.innerHTML = '<div class="placeholder">点击按钮开始录音，识别结果将显示在这里...</div>';
            this.resultEl.classList.remove('success');
        } else {
            this.resultEl.innerHTML = `<div class="result-text">${escapeHtml(text)}</div>`;
            this.resultEl.classList.add('success');
        }
    }

    updateSendBtn() {
        if (this.sendToAiBtn) {
            this.sendToAiBtn.disabled = !this.recognizedText.trim();
        }
    }

    updateUI() {
        const btnText = this.recordBtn.querySelector('.btn-text');
        if (this.isRecording) {
            this.recordBtn.classList.add('recording');
            this.statusEl.classList.add('recording');
            if (btnText) btnText.textContent = '停止录音';
        } else {
            this.recordBtn.classList.remove('recording');
            this.statusEl.classList.remove('recording');
            if (btnText) btnText.textContent = '开始录音';
        }
    }

    updateStatus(text, isRecording = false) {
        this.statusEl.textContent = text;
        if (isRecording) this.statusEl.classList.add('recording');
        else this.statusEl.classList.remove('recording');
    }

    handleSpeechError(error) {
        const msgs = {
            'no-speech': '未检测到语音，请重试',
            'audio-capture': '无法访问麦克风，请检查权限',
            'not-allowed': '麦克风权限被拒绝',
            'network': '网络错误',
            'aborted': '识别已中断',
        };
        const msg = msgs[error] || `识别出错: ${error}`;
        this.resultEl.innerHTML = `<div class="error">${msg}</div>`;
        this.addDebugLog(`错误: ${msg}`);
    }

    addDebugLog(message) {
        const ts = new Date().toLocaleTimeString();
        this.debugLogs.push(`[${ts}] ${message}`);
        if (this.debugLogs.length > 80) this.debugLogs = this.debugLogs.slice(-80);
        if (this.debugLogEl) {
            this.debugLogEl.textContent = this.debugLogs.join('\n');
            this.debugLogEl.scrollTop = this.debugLogEl.scrollHeight;
        }
    }
}

// ── 全局辅助：HTML 转义 ──
function escapeHtml(text) {
    return String(text)
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;');
}

// 启动
document.addEventListener('DOMContentLoaded', () => {
    new SpeechAIApp();
});
