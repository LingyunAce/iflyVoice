/**
 * main.js — 语音 AI 助手主控制器
 * 负责：语音识别（浏览器 / 讯飞）+ AI 对话（本地 Ollama / 云端火山引擎） + UI 联动
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
        this.modelSourceSel  = document.getElementById('modelSource');   // 模型源切换

        // ── AI 客户端（支持 Ollama 本地 / 火山引擎云端）──
        this.ollama = null;      // OllamaClient 实例
        this.cloud  = null;     // CloudClient 实例
        this.aiClient = null;   // 当前活跃的客户端（指向 ollama 或 cloud）
        this.currentSource = 'local';  // 'local' | 'cloud'

        // ── I2C 显示器控制器 ──
        this.i2c = null;

        // ── 内置屏幕控制器 ──
        this.nativeDisplay = null;
        this.displayType = 'adb';  // 'adb' | 'native'

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
        this.initI2cPanel();
        this.initModelSourceSwitch();  // 模型源切换
        await this.initOllama();
    }

    // ── 初始化 AI 客户端（根据当前模型源）──
    async initOllama() {
        if (this.currentSource === 'cloud') {
            // 云端模式：使用静态模型列表
            const models = CloudClient.getModels();
            this.modelSelector.innerHTML = '';
            models.forEach(m => {
                const opt = document.createElement('option');
                opt.value = m.id;
                opt.textContent = m.name;
                if (m.id === CLOUD_CONFIG.defaultModel) opt.selected = true;
                this.modelSelector.appendChild(opt);
            });
            this.addDebugLog(`云端模型已加载: ${models.map(m => m.name).join(', ')}`);
        } else {
            // 本地模式：从 Ollama 获取模型列表
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
        }

        this.createAiClient();

        // 模型切换时重建客户端
        this.modelSelector.addEventListener('change', () => {
            this.createAiClient();
            this.addDebugLog(`切换模型: ${this.modelSelector.value}`);
        });
    }

    /**
     * 模型源切换（本地/云端）
     */
    initModelSourceSwitch() {
        if (!this.modelSourceSel) return;

        this.modelSourceSel.addEventListener('change', async () => {
            this.currentSource = this.modelSourceSel.value;
            this.addDebugLog(`切换模型源: ${this.currentSource === 'cloud' ? '火山引擎(云端)' : 'Ollama(本地)'}`);

            if (this.aiClient) { this.aiClient.abort(); this.aiClient = null; }
            await this.initOllama();
        });
    }

    createAiClient() {
        // 如果上一个正在生成，先中断
        if (this.aiClient) this.aiClient.abort();

        if (this.currentSource === 'cloud') {
            // 云端模式：使用 CloudClient
            this.cloud = new CloudClient({
                model: this.modelSelector.value || CLOUD_CONFIG.defaultModel,
                onToken: (token, full) => {
                    this.updateStreamingBubble(full);
                },
                onDone: (clean, raw) => {
                    this.finalizeAssistantBubble(clean);
                    this.setGenerating(false);
                },
                onError: (err) => {
                    this.appendErrorBubble(`云端模型错误: ${err.message}`);
                    this.setGenerating(false);
                },
            });
            this.aiClient = this.cloud;
        } else {
            // 本地模式：使用 OllamaClient
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
            this.aiClient = this.ollama;
        }
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
            if (this.aiClient) this.aiClient.abort();
            this.setGenerating(false);
            this.finalizeAssistantBubble(this._streamingText || '（已中断）');
            this.addDebugLog('用户中断生成');
        });

        // 清空对话
        this.clearChatBtn.addEventListener('click', () => {
            if (this.aiClient) { this.aiClient.abort(); this.aiClient.clearHistory(); }
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
        if (!text || this.aiClient?.isGenerating) return;
        this.chatInput.value = '';
        this.sendToOllama(text);
    }

    // ═══════════════════════════════════════
    //  发送消息给 AI（本地/云端统一接口）
    // ═══════════════════════════════════════
    async sendToOllama(text) {
        if (!this.aiClient) { this.appendErrorBubble('AI 客户端未初始化'); return; }
        if (this.aiClient.isGenerating) { this.addDebugLog('上一条回答还在生成中，请稍候'); return; }

        // ── 检测显示器控制指令（并行执行 i2cset，不拦截 AI 对话）──
        const i2cIntent = this.tryExecuteI2cCommand(text);

        // 移除欢迎语
        const welcome = this.chatMessages.querySelector('.chat-welcome');
        if (welcome) welcome.remove();

        // 显示用户气泡
        this.appendUserBubble(text);
        this.addDebugLog(`发送给 ${this.currentSource === 'cloud' ? '云端' : '本地'}AI: ${text}`);

        // 创建 AI 气泡（思考中）
        this._streamingText = '';
        this._streamingBubbleEl = this.appendAssistantBubble();

        this.setGenerating(true);
        const modelName = this.aiClient.model || 'unknown';
        this.setAiStatus(`${modelName} 正在思考...`);

        try {
            // 如果检测到 I2C 控制指令，在消息前注入上下文提示 AI 已执行操作
            let sendText = text;
            if (i2cIntent) {
                const controlLabels = { brightness: '亮度', contrast: '对比度', powerMode: '电源' };
                const ctrlLabel = controlLabels[i2cIntent.control] || i2cIntent.control;

                if (i2cIntent.cannotAdjust) {
                    // 已达极限，无法再调
                    const dir = (i2cIntent.delta || 0) > 0 ? '最高' : '最低';
                    const cur = i2cIntent.currentVal ?? (this.displayType === 'native'
                        ? (i2cIntent.control === 'brightness' ? this.brightnessSlider?.value : this.contrastSlider?.value)
                        : 50);
                    sendText = `[系统提示：用户要求调整${ctrlLabel}，但${ctrlLabel}已经是${cur}（${dir}），无法再调整。请友好地告知用户这一点，不要说"无法操作设备"。]\n\n用户消息：${text}`;
                    this.addDebugLog(`[I2C] 已达极限，跳过命令，注入AI: ${ctrlLabel}=${cur}`);
                } else {
                    let detail = '';
                    if (i2cIntent.action === 'set') {
                        detail = `已将${ctrlLabel}调整为 ${i2cIntent.value}%`;
                    } else if (i2cIntent.action === 'adjust') {
                        const dir = (i2cIntent.delta || 0) > 0 ? '调高' : '调低';
                        detail = `已将${ctrlLabel}${dir}`;
                    }
                    sendText = `[系统提示：${detail}，I2C命令已直接执行。请确认操作结果并友好回复用户，不要说"无法操作设备"。]\n\n用户消息：${text}`;
                    this.addDebugLog(`[I2C] 注入AI上下文: ${detail}`);
                }
            }

            await this.aiClient.chat(sendText);
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

    // ═══════════════════════════════════════
    //  I2C 显示器控制面板
    // ═══════════════════════════════════════

    initI2cPanel() {
        // 创建控制器实例
        this.i2c = new window.I2cController();

        // DOM 引用
        this.brightnessSlider = document.getElementById('brightnessSlider');
        this.contrastSlider   = document.getElementById('contrastSlider');
        this.brightnessValue = document.getElementById('brightnessValue');
        this.contrastValue   = document.getElementById('contrastValue');
        this.adbCheckBtn     = document.getElementById('adbCheckBtn');
        this.adbDeviceInfo   = document.getElementById('adbDeviceInfo');
        this.nativeCheckBtn  = document.getElementById('nativeCheckBtn');
        this.nativeDeviceInfo = document.getElementById('nativeDeviceInfo');
        this.i2cStatusDot    = document.getElementById('i2cStatusDot');
        this.i2cStatusText   = document.getElementById('i2cStatusText');
        this.i2cCmdLog       = document.getElementById('i2cCmdLog');
        this.displayTypeSel  = document.getElementById('displayType');
        this.adbSection      = document.getElementById('adbSection');
        this.nativeSection   = document.getElementById('nativeSection');

        // 显示器类型切换
        if (this.displayTypeSel) {
            this.displayTypeSel.addEventListener('change', (e) => {
                this.displayType = e.target.value;
                this._updateDisplayTypeUI();
                this._initDisplayController();
                this.addDebugLog(`切换显示器类型: ${this.displayType === 'adb' ? 'ADB 显示器' : '内置屏幕'}`);
            });
        }

        // 同步 displayType（构造函数里是硬编码默认值，要以 HTML selected 为准）
        if (this.displayTypeSel) {
            this.displayType = this.displayTypeSel.value;
        }

        // 初始化当前类型的控制器
        this._initDisplayController();

        // 状态回调（ADB）
        this.i2c.onStatusChange = (status, data) => {
            this.updateI2cStatus(status, data);
        };

        // 亮度滑块
        if (this.brightnessSlider) {
            this.brightnessSlider.addEventListener('input', () => {
                const val = parseInt(this.brightnessSlider.value);
                this.brightnessValue.textContent = val;
            });
            this.brightnessSlider.addEventListener('change', () => {
                const val = parseInt(this.brightnessSlider.value);
                this.executeI2cCommand('brightness', val);
            });
        }

        // 对比度滑块
        if (this.contrastSlider) {
            this.contrastSlider.addEventListener('input', () => {
                const val = parseInt(this.contrastSlider.value);
                this.contrastValue.textContent = val;
            });
            this.contrastSlider.addEventListener('change', () => {
                const val = parseInt(this.contrastSlider.value);
                this.executeI2cCommand('contrast', val);
            });
        }

        // ADB 检测按钮
        if (this.adbCheckBtn) {
            this.adbCheckBtn.addEventListener('click', () => this.checkAdbConnection());
        }

        // 内置屏幕检测按钮
        if (this.nativeCheckBtn) {
            this.nativeCheckBtn.addEventListener('click', () => this.checkNativeConnection());
        }

        // 快捷按钮
        document.querySelectorAll('.quick-actions .monitor-btn').forEach(btn => {
            btn.addEventListener('click', (e) => {
                const action = e.target.dataset.action;
                const value = parseInt(e.target.dataset.value);
                if (action === 'powerMode') {
                    this.executeI2cCommand(action, value);
                } else if (action === 'brightness') {
                    this.brightnessSlider.value = value;
                    this.brightnessValue.textContent = value;
                    this.executeI2cCommand('brightness', value);
                }
            });
        });

        // 启动时自动检测
        setTimeout(() => {
            this._initDisplayController();
        }, 500);

        this.addDebugLog('I2C 显示器控制面板已初始化');
    }

    /** 根据 displayType 切换 UI 显示 */
    _updateDisplayTypeUI() {
        if (!this.adbSection || !this.nativeSection) return;
        if (this.displayType === 'native') {
            this.adbSection.style.display = 'none';
            this.nativeSection.style.display = 'flex';
        } else {
            this.adbSection.style.display = 'flex';
            this.nativeSection.style.display = 'none';
        }
    }

    /** 初始化当前类型的显示器控制器 */
    _initDisplayController() {
        if (this.displayType === 'native') {
            if (!this.nativeDisplay) {
                this.nativeDisplay = new window.NativeDisplayClient();
            }
            // 启动时自动检测连接状态
            setTimeout(() => this.checkNativeConnection(), 800);
            this._updateDisplayTypeUI();
        } else {
            setTimeout(() => this.checkAdbConnection(), 800);
            this._updateDisplayTypeUI();
        }
    }

    async checkAdbConnection() {
        if (!this.adbCheckBtn) return;
        this.adbCheckBtn.disabled = true;
        this.adbCheckBtn.textContent = '检测中...';
        try {
            const result = await this.i2c.checkConnection();
            if (result.connected) {
                this.adbDeviceInfo.textContent = `✅ ${result.deviceCount} 台设备`;
                this.addDebugLog(`ADB 已连接: ${result.devices.join(', ')}`);
            } else {
                this.adbDeviceInfo.textContent = `❌ ${result.error || '无设备'}`;
                this.addDebugLog(`ADB 未连接: ${result.error || '无设备'}`);
            }
        } catch (e) {
            this.adbDeviceInfo.textContent = `❌ ${e.message}`;
            this.addDebugLog(`ADB 检测异常: ${e.message}`);
        } finally {
            this.adbCheckBtn.disabled = false;
            this.adbCheckBtn.textContent = '检测设备';
        }
    }

    updateI2cStatus(status, data) {
        const dot = this.i2cStatusDot;
        const txt = this.i2cStatusText;
        if (!dot || !txt) return;

        dot.className = 'status-dot';
        switch (status) {
            case 'connected':
                dot.classList.add('status-dot-on'); txt.textContent = '已连接'; break;
            case 'disconnected':
                dot.classList.add('status-dot-off'); txt.textContent = '未连接'; break;
            case 'executing':
                dot.classList.add('status-dot-busy'); txt.textContent = '执行中...'; break;
            default:
                dot.classList.add('status-dot-off'); txt.textContent = status; break;
        }
    }

    /**
     * 执行 I2C DDC/CI 命令（带防抖 + 状态反馈）
     */
    async executeI2cCommand(controlName, value) {
        this.updateI2cStatus('executing');
        this.addDebugLog(`[Display] 设置 ${controlName} = ${value}`);

        if (this.displayType === 'native') {
            // 内置屏幕：WMI / DDC/CI
            await this._executeNativeCommand(controlName, value);
        } else {
            // ADB 显示器：DDC/CI over ADB
            await this._executeAdbCommand(controlName, value);
        }
    }

    async _executeNativeCommand(controlName, value) {
        if (!this.nativeDisplay) {
            this.nativeDisplay = new window.NativeDisplayClient();
        }

        try {
            let result;
            if (controlName === 'brightness') {
                result = await this.nativeDisplay.setBrightness(value);
                this.appendI2cLog(`[Native] 亮度=${value}%`);
            } else if (controlName === 'contrast') {
                // 对比度走 DDC/CI（和 ADB 显示器相同）
                result = await this._executeAdbCommand(controlName, value);
                this.appendI2cLog(`[Native] 对比度=${value}%`);
                return; // _executeAdbCommand 内部已处理状态更新
            } else {
                this.updateI2cStatus('error');
                return;
            }

            if (result.success) {
                this.addDebugLog(`[Native] ✓ ${controlName}=${value} 成功`);
                this.updateI2cStatus(this.nativeDisplay.connected ? 'connected' : 'disconnected');
                // 回读确认：确保滑块与硬件真实值同步（WMI 可能静默失败）
                const current = await this.nativeDisplay.getBrightness();
                if (current != null) {
                    const actual = Math.round(current);
                    this.brightnessSlider.value = actual;
                    this.brightnessValue.textContent = actual;
                    this.addDebugLog(`[Native] 回读确认: 实际亮度=${actual}%`);
                }
            } else {
                this.addDebugLog(`[Native] ✗ 失败: ${result.error}`);
                this.appendI2cLog(`错误: ${result.error}`, true);
                this.updateI2cStatus('error');
                // 回读当前值同步 UI
                const current = await this.nativeDisplay.getBrightness();
                if (current != null) {
                    const actual = Math.round(current);
                    this.brightnessSlider.value = actual;
                    this.brightnessValue.textContent = actual;
                }
            }
        } catch (e) {
            this.addDebugLog(`[Native] ✗ 异常: ${e.message}`);
            this.appendI2cLog(`异常: ${e.message}`, true);
            this.updateI2cStatus('error');
        }
    }

    async _executeAdbCommand(controlName, value) {
        if (!this.i2c) return;

        try {
            const cmdInfo = buildDdcCiCommand(
                I2C_CONFIG.VCP_CODES[controlName] || 0x10,
                controlName === 'powerMode' ? value : value
            );
            this.appendI2cLog(cmdInfo.cmdStr);

            const result = await this.i2c.setControl(controlName, value);
            this.addDebugLog(`[ADB] ✓ ${controlName}=${value} 成功`);
            this.updateI2cStatus(this.i2c.connected ? 'connected' : 'disconnected');
        } catch (e) {
            this.addDebugLog(`[ADB] ✗ 失败: ${e.message}`);
            this.appendI2cLog(`错误: ${e.message}`, true);
            this.updateI2cStatus('error');
        }
    }

    async checkNativeConnection() {
        if (!this.nativeCheckBtn) return;
        this.nativeCheckBtn.disabled = true;
        this.nativeCheckBtn.textContent = '检测中...';
        try {
            if (!this.nativeDisplay) {
                this.nativeDisplay = new window.NativeDisplayClient();
            }
            const result = await this.nativeDisplay.checkConnection();
            if (result.connected) {
                this.nativeDeviceInfo.textContent = `✅ 已连接`;
                this.addDebugLog(`内置屏幕已连接 (亮度 ${result.brightness}%)`);
                this.updateI2cStatus('connected');
                // 用检测到的当前亮度更新滑块
                if (result.brightness != null) {
                    this.brightnessSlider.value = result.brightness;
                    this.brightnessValue.textContent = result.brightness;
                }
            } else {
                this.nativeDeviceInfo.textContent = `❌ ${result.error || '不可用'}`;
                this.addDebugLog(`内置屏幕不可用: ${result.error}`);
                this.updateI2cStatus('disconnected');
            }
        } catch (e) {
            this.nativeDeviceInfo.textContent = `❌ ${e.message}`;
            this.addDebugLog(`内置屏幕检测异常: ${e.message}`);
            this.updateI2cStatus('disconnected');
        } finally {
            this.nativeCheckBtn.disabled = false;
            this.nativeCheckBtn.textContent = '检测连接';
        }
    }

    appendI2cLog(text, isError = false) {
        if (!this.i2cCmdLog) return;
        const ts = new Date().toLocaleTimeString();
        const line = `[${ts}] ${text}\n`;
        this.i2cCmdLog.textContent += line;
        this.i2cCmdLog.scrollTop = this.i2cCmdLog.scrollHeight;
        if (isError && this.i2cCmdLog) {
            this.i2cCmdLog.style.color = '#ff6b7a';
        } else if (this.i2cCmdLog) {
            this.i2cCmdLog.style.color = '#7ec8e3';
        }
    }

    /**
     * 检测文本中的显示器控制指令，并行执行 i2cset（不拦截 AI 对话）
     * 效果：用户说"亮度调到50" → 同时执行 i2cset + 照常发给 AI 回复 + 同步更新滑块 UI
     * @returns {object|null} 检测到的控制意图对象（用于注入 AI 上下文）
     */
    tryExecuteI2cCommand(text) {
        // ADB 模式必须有 i2c 控制器；内置屏幕模式不需要预初始化
        if (this.displayType !== 'native' && !this.i2c) return null;

        const intent = this.i2c.parseVoiceCommand(text);
        if (!intent) return null;

        // 内置屏幕不支持电源控制（WMI 无此接口）
        if (this.displayType === 'native' && intent.control === 'powerMode') {
            return null; // 静默忽略
        }

        this.addDebugLog(`[I2C] 检测到控制指令: action=${intent.action} control=${intent.control} value=${intent.value || intent.delta || ''}`);

        if (intent.action === 'set') {
            let targetVal = intent.value;

            // 电源控制
            if (intent.control === 'powerMode') {
                const powerLabels = { 0x01: '唤醒', 0x06: '关闭' };
                this.addDebugLog(`[I2C] 🖥️ [显示器] ${powerLabels[targetVal] || targetVal}`);
                this.executeI2cCommand(intent.control, targetVal);
                return intent;
            }

            // 亮度/对比度等 0-100 范围的控制 — 更新滑块 UI
            if (intent.control === 'brightness' && this.brightnessSlider) {
                this.brightnessSlider.value = targetVal;
                this.brightnessValue.textContent = targetVal;
            } else if (intent.control === 'contrast' && this.contrastSlider) {
                this.contrastSlider.value = targetVal;
                this.contrastValue.textContent = targetVal;
            }

            this.addDebugLog(`[I2C] 🖥️ [${intent.control}] → ${targetVal}%，已同步滑块`);
            // 非阻塞执行 i2cset（fire-and-forget）
            this.executeI2cCommand(intent.control, targetVal);

        } else if (intent.action === 'adjust') {
            const slider = intent.control === 'brightness' ? this.brightnessSlider : this.contrastSlider;
            if (!slider) return intent;

            let current = parseInt(slider.value) ?? 50;
            let targetVal = Math.max(0, Math.min(100, current + intent.delta));

            // 检测是否已到极限，调不了
            if (targetVal === current) {
                intent.cannotAdjust = true;
                intent.currentVal = current;
                this.addDebugLog(`[I2C] 🖥️ [${intent.control}] 已达极限(${current})，无需调整`);
                return intent;
            }

            const direction = intent.delta > 0 ? '↑' : '↓';
            slider.value = targetVal;
            if (intent.control === 'brightness' && this.brightnessValue) {
                this.brightnessValue.textContent = targetVal;
            } else if (intent.control === 'contrast' && this.contrastValue) {
                this.contrastValue.textContent = targetVal;
            }

            this.addDebugLog(`[I2C] 🖥️ [${intent.control}] ${direction} ${targetVal}%，已同步滑块`);
            this.executeI2cCommand(intent.control, targetVal);
        }

        return intent;
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
