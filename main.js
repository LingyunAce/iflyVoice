/**
 * main.js — 语音 AI 助手主控制器
 * 负责：语音识别（浏览器 / 讯飞 / SenseVoice）+ AI 对话（本地 Ollama qwen3:8b）+ UI 联动
 */
class SpeechAIApp {
    constructor() {
        // ── 语音识别相关 ──
        this.mediaRecorder = null;
        this.audioChunks = [];
        this.isRecording = false;
        this.recognizedText = '';
        this.debugLogs = [];
        this.recordTimer = null;
        this.maxRecordTime = 30000;

    // ── DOM 元素 ──
    this.recordBtn       = document.getElementById('recordBtn');
    this.statusEl        = document.getElementById('status');   // 可能为 null（左侧面板已删除）
    this.debugLogEl      = document.getElementById('debugLog');
    this.micSelect       = document.getElementById('micSelect');
    this.resultPreview   = document.getElementById('resultPreview');  // 可能为 null
    this.chatMessages    = document.getElementById('chatMessages');
    this.chatInput       = document.getElementById('chatInput');
    this.chatSendBtn     = document.getElementById('chatSendBtn');
    this.stopGenBtn      = document.getElementById('stopGenBtn');
    this.aiStatusEl      = document.getElementById('aiStatus');
    this.clearChatBtn    = document.getElementById('clearChatBtn');

        // ── AI 客户端（Ollama qwen3:8b）──
        this.ollama = null;      // OllamaClient 实例
        this.aiClient = null;   // 当前活跃的客户端

        // ── I2C 显示器控制器（ADB，备用）──
        this.i2c = null;

        // ── 内置屏幕控制器 ──
        this.nativeDisplay = null;

        // ── 外置屏幕 DDC/CI 控制器 (dxva2.dll) ──
        this.ddcci = null;

        this.displayType = 'adb';  // 'adb' | 'native'

        this.init();
    }

    // ═══════════════════════════════════════
    //  初始化
    // ═══════════════════════════════════════
    async init() {
        this.bindSpeechEvents();
        this.bindChatEvents();
        this.initI2cPanel();
        await this.loadAudioDevices();  // 加载麦克风列表
        await this.initOllama();       // 初始化 AI 客户端
    }

    // ── 初始化 AI 客户端 ────────────────────────────────
    async initOllama() {
        try {
            const models = await OllamaClient.fetchModels();
            if (models.length > 0) {
                this.addDebugLog(`Ollama 已连接，可用模型: ${models.join(', ')}`);
            } else {
                this.addDebugLog('⚠ Ollama 未响应或无可用模型');
                this.setAiStatus('⚠ Ollama 未连接');
            }
        } catch (e) {
            this.addDebugLog(`Ollama 连接失败: ${e.message}`);
            this.setAiStatus('⚠ Ollama 未连接');
        }
        this.createAiClient();
    }

    createAiClient() {
        // 如果上一个正在生成，先中断
        if (this.aiClient) this.aiClient.abort();

        const model = this.modelNameInput?.value?.trim() || 'qwen3:8b';
        this.ollama = new OllamaClient({
            model: model,
            onToken: (token, full) => {
                this.updateStreamingBubble(full);
            },
            onDone: (clean, raw) => {
                this.finalizeAssistantBubble(clean);
                this.setGenerating(false);
            },
            onError: (err) => {
                this.appendErrorBubble(`AI 错误: ${err.message}`);
                this.setGenerating(false);
            },
        });
        this.aiClient = this.ollama;
    }

    /** 应用 Ollama URL + 模型变更 */
    _applyOllamaUrl() {
        const url = (this.ollamaUrlInput?.value || '').trim();
        const model = (this.modelNameInput?.value || 'qwen3:8b').trim();
        if (!url) return;
        // 提取 host:port
        const colonIdx = url.lastIndexOf(':');
        const host = url.substring(0, colonIdx);
        const port = parseInt(url.substring(colonIdx + 1), 10);
        if (host && port > 0) {
            // 通知 server.py 更新 Ollama 配置
            fetch('/config/ollama', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ host, port, model }),
            }).then(r => r.json()).then(data => {
                this.addDebugLog(`Ollama 已更新: ${host}:${port} / ${model}`);
                // 用新模型重建 AI 客户端
                this.createAiClient();
            }).catch(e => {
                this.addDebugLog(`Ollama 配置更新失败: ${e.message}`);
            });
        }
    }

    /** 应用语音识别服务 URL 变更 */
    _applySensevoiceUrl() {
        const url = (this.sensevoiceUrlInput?.value || '').trim();
        if (!url) return;
        fetch('/config/sensevoice', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ base_url: url }),
        }).then(r => r.json()).then(data => {
            this.addDebugLog(`语音识别服务已更新: ${url}`);
        }).catch(e => {
            this.addDebugLog(`语音识别配置更新失败: ${e.message}`);
        });
    }

    // ═══════════════════════════════════════
    //  加载麦克风设备列表
    // ═══════════════════════════════════════
    async loadAudioDevices() {
        if (!this.micSelect) return;
        try {
            // 先申请权限，否则 label 为空
            const tempStream = await navigator.mediaDevices.getUserMedia({ audio: true });
            tempStream.getTracks().forEach(t => t.stop());

            const devices = await navigator.mediaDevices.enumerateDevices();
            const inputs = devices.filter(d => d.kind === 'audioinput');

            this.micSelect.innerHTML = '';
            if (inputs.length === 0) {
                this.micSelect.innerHTML = '<option value="">未检测到麦克风</option>';
                return;
            }

            // 默认项：系统默认设备
            const defaultOpt = document.createElement('option');
            defaultOpt.value = '';
            defaultOpt.textContent = '默认麦克风';
            this.micSelect.appendChild(defaultOpt);

            inputs.forEach(dev => {
                const opt = document.createElement('option');
                opt.value = dev.deviceId;
                opt.textContent = dev.label || `麦克风 (${dev.deviceId.slice(0, 8)})`;
                this.micSelect.appendChild(opt);
            });

            this.addDebugLog(`检测到 ${inputs.length} 个麦克风设备`);
        } catch (e) {
            this.addDebugLog(`加载麦克风列表失败: ${e.message}`);
            this.micSelect.innerHTML = '<option value="">无法访问麦克风</option>';
        }
    }

    // ═══════════════════════════════════════
    //  绑定语音录音事件
    // ═══════════════════════════════════════
    bindSpeechEvents() {
        this.recordBtn.addEventListener('click', () => this.handleRecordClick());
    }

    async handleRecordClick() {
        this.isRecording ? await this.stopRecording() : await this.startRecording();
    }

    async startRecording() {
        if (this.isRecording) return;
        this.recognizedText = '';

        try {
            // SenseVoice：通过 MediaRecorder 录音，结束后上传到服务器
            if (!window.SenseVoiceClient) { this.addDebugLog('SenseVoice 模块未加载'); return; }
            this.audioChunks = [];
            // 使用选定的麦克风设备
            const audioConstraints = { audio: true, video: false };
            if (this.micSelect && this.micSelect.value) {
                audioConstraints.audio = { deviceId: { exact: this.micSelect.value } };
            }
            const stream = await navigator.mediaDevices.getUserMedia(audioConstraints);
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
            this.appendErrorBubble(`录音失败: ${err.message}`);
        }
    }


    async stopRecording() {
        if (!this.isRecording) return;
        this.addDebugLog('停止录音...');
        if (this.recordTimer) { clearTimeout(this.recordTimer); this.recordTimer = null; }

        // SenseVoice: 停止录音并识别 → 识别完自动发给 AI
        if (this.mediaRecorder) {
            this.mediaRecorder.stop();
            this.mediaRecorder.stream.getTracks().forEach(t => t.stop());
            await new Promise(resolve => setTimeout(resolve, 300));
            if (this.audioChunks.length === 0) {
                this.addDebugLog('SenseVoice: 无音频数据');
                this.isRecording = false;
                this.updateUI();
                this.updateStatus('准备就绪');
                return;
            }
            const audioBlob = new Blob(this.audioChunks, { type: this.audioChunks[0].type || 'audio/webm' });
            this.addDebugLog('SenseVoice 正在识别...');
            this.updateStatus('正在识别...');

            try {
                const sv = new window.SenseVoiceClient();
                const result = await sv.transcribe(audioBlob);
                if (result.success && result.text && result.text.trim()) {
                    this.recognizedText = result.text.trim();
                    this.addDebugLog(`✅ 识别: "${this.recognizedText}"`);
                    // 更新左侧预览区
                    this._updateResultPreview(this.recognizedText);
                    // ⚡ 直接发送给 AI，无需手动点击
                    this.sendToOllama(this.recognizedText);
                } else {
                    this.addDebugLog(`⚠ 识别无结果或失败: ${result.error || 'empty'}`);
                    this.appendErrorBubble(`语音识别未返回内容：${result.error || '请重试'}`);
                }
            } catch (e) {
                this.addDebugLog(`SenseVoice 请求异常: ${e.message}`);
                this.appendErrorBubble(`语音识别异常: ${e.message}`);
            }
            this.mediaRecorder = null;
        }

        this.isRecording = false;
        this.updateUI();
        this.updateStatus('准备就绪');
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

        // ── 检测显示器控制指令（并行执行 i2cset）──
        const i2cIntent = this.tryExecuteI2cCommand(text);

        // 移除欢迎语
        const welcome = this.chatMessages.querySelector('.chat-welcome');
        if (welcome) welcome.remove();

        // 显示用户气泡
        this.appendUserBubble(text);
        this.addDebugLog(`发送给本地 AI: ${text}`);

        // ═══ 优化：亮度/对比度调节 → 立即回复，不等 Ollama ═══
        const QUICK_CONTROLS = ['brightness', 'contrast', 'volume'];
        if (i2cIntent && QUICK_CONTROLS.includes(i2cIntent.control)) {
            const controlLabels = { brightness: '亮度', contrast: '对比度', volume: '音量' };
            const ctrlLabel = controlLabels[i2cIntent.control];

            if (i2cIntent.cannotAdjust) {
                const dir = (i2cIntent.delta || 0) > 0 ? '最高' : '最低';
                const cur = i2cIntent.currentVal ?? 50;
                this._showImmediateReply(`好的，${ctrlLabel}已经是 ${cur}%（已到${dir}），不能再调整了。`);
            } else {
                let msg = '';
                let finalVal = null;
                if (i2cIntent.action === 'set') {
                    finalVal = i2cIntent.value;
                    msg = `好的，已将${ctrlLabel}设为 ${finalVal}%。`;
                } else {
                    const dir = (i2cIntent.delta || 0) > 0 ? '调高' : '调低';
                    let slider;
                    if (i2cIntent.control === 'brightness') slider = this.brightnessSlider;
                    else if (i2cIntent.control === 'contrast') slider = this.contrastSlider;
                    else if (i2cIntent.control === 'volume') slider = this.volumeSlider;
                    finalVal = parseInt(slider?.value ?? 50);
                    msg = `好的，已将${ctrlLabel}${dir}，当前 ${finalVal}%。`;
                }
                this._showImmediateReply(msg);
                this.addDebugLog(`[I2C] ⚡ 即时回复: ${msg}`);
            }

            // Ollama 后台异步补充（不阻塞用户）
            this._aiBackgroundChat(text, i2cIntent).catch(e => {
                this.addDebugLog(`[I2C] 后台AI补充失败(可忽略): ${e.message}`);
            });
            return;
        }

        // ═══ 其他情况：走正常 AI 流程（色温/伽马/电源/普通对话）═══
        this._streamingText = '';
        this._streamingBubbleEl = this.appendAssistantBubble();

        this.setGenerating(true);
        const modelName = this.aiClient.model || 'unknown';
        this.setAiStatus(`${modelName} 正在思考...`);

        try {
            let sendText = text;
            if (i2cIntent) {
                const controlLabels = { brightness: '亮度', contrast: '对比度', colorTemp: '色温', gamma: '伽马', powerMode: '电源' };
                const ctrlLabel = controlLabels[i2cIntent.control] || i2cIntent.control;

                if (i2cIntent.cannotAdjust) {
                    const dir = (i2cIntent.delta || 0) > 0 ? '最高' : '最低';
                    let cur = i2cIntent.currentVal;
                    if (cur == null) {
                        if (i2cIntent.control === 'brightness') cur = this.brightnessSlider?.value;
                        else if (i2cIntent.control === 'contrast') cur = this.contrastSlider?.value;
                        else if (i2cIntent.control === 'colorTemp') cur = this.colorTempSlider?.value;
                        else if (i2cIntent.control === 'gamma') cur = this.gammaSlider?.value;
                    }
                    cur = cur ?? 50;
                    sendText = `[系统提示：用户要求调整${ctrlLabel}，但${ctrlLabel}已经是${cur}（${dir}）。请友好告知。]\n\n用户消息：${text}`;
                } else {
                    let detail = '';
                    if (i2cIntent.action === 'set') {
                        detail = `已将${ctrlLabel}调整为 ${i2cIntent.value}%`;
                    } else if (i2cIntent.action === 'adjust') {
                        const dir = (i2cIntent.delta || 0) > 0 ? '调高' : '调低';
                        detail = `已将${ctrlLabel}${dir}`;
                    }
                    sendText = `[系统提示：${detail}，硬件命令已执行。请确认并友好回复。]\n\n用户消息：${text}`;
                }
            }

            await this.aiClient.chat(sendText);
        } catch (e) {
            // 错误已由 onError 回调处理
        }
    }

    /**
     * 立即显示助手回复（不走 AI，毫秒级响应）
     */
    _showImmediateReply(message) {
        const el = document.createElement('div');
        el.className = 'message assistant';
        el.innerHTML = `
            <div class="message-avatar">&#129504;</div>
            <div class="message-bubble">${message}</div>`;
        this.chatMessages.appendChild(el);
        this.scrollToBottom();
        this.setAiStatus('');
    }

    /**
     * Ollama 后台异步聊天（用于亮度/对比度即时回复后的补充）
     * 失败静默处理，不影响已展示的即时回复
     */
    async _aiBackgroundChat(originalText, i2cIntent) {
        try {
            const controlLabels = { brightness: '亮度', contrast: '对比度' };
            const ctrlLabel = controlLabels[i2cIntent.control] || i2cIntent.control;
            let detail = '';
            if (i2cIntent.action === 'set') {
                detail = `已将${ctrlLabel}调整为 ${i2cIntent.value}%`;
            } else if (i2cIntent.action === 'adjust') {
                const dir = (i2cIntent.delta || 0) > 0 ? '调高' : '调低';
                detail = `已将${ctrlLabel}${dir}`;
            }
            const sendText = `[系统提示：${detail}，硬件命令已直接执行完成。请用一句话简洁确认即可，不超过20字。]\n\n用户消息：${originalText}`;

            // 创建临时客户端避免冲突
            const tmpClient = new OllamaClient({
                model: 'qwen3:8b',
                onToken: () => {},      // 不流式显示
                onDone: (clean) => {
                    // AI 回来后，追加一条小提示（可选）
                    if (clean && clean.trim() && clean.length < 50) {
                        this.addDebugLog(`[I2C] AI后台补充: ${clean.trim()}`);
                    }
                },
                onError: () => {},
            });
            await tmpClient.chat(sendText);
        } catch (e) {
            // 静默——即时回复已经显示了，AI 补充失败不影响体验
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
    updateUI() {
        const btnText = this.recordBtn.querySelector('.voice-text');
        if (this.isRecording) {
            this.recordBtn.classList.add('recording');
            if (this.statusEl) this.statusEl.classList.add('recording');
            if (btnText) btnText.textContent = '停止录音';
        } else {
            this.recordBtn.classList.remove('recording');
            if (this.statusEl) this.statusEl.classList.remove('recording');
            if (btnText) btnText.textContent = '语音输入';
        }
    }

    updateStatus(text, isRecording = false) {
        if (this.statusEl) {
            this.statusEl.textContent = text;
            if (isRecording) this.statusEl.classList.add('recording');
            else this.statusEl.classList.remove('recording');
        }
    }

    /** 更新左侧识别结果预览区 */
    _updateResultPreview(text) {
        if (!this.resultPreview) return;
        if (text) {
            this.resultPreview.innerHTML = `<span class="result-text">${escapeHtml(text)}</span>`;
            this.resultPreview.classList.add('has-result');
        } else {
            this.resultPreview.innerHTML = '<span class="preview-placeholder">等待语音输入...</span>';
            this.resultPreview.classList.remove('has-result');
        }
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
        this.volumeSlider     = document.getElementById('volumeSlider');
        this.brightnessValue = document.getElementById('brightnessValue');
        this.contrastValue   = document.getElementById('contrastValue');
        this.volumeValue     = document.getElementById('volumeValue');
        this.adbCheckBtn     = document.getElementById('adbCheckBtn');
        // adbDeviceInfo / adbSection 已移除（顶部 i2cStatus 已覆盖连接状态）
        this.nativeCheckBtn  = document.getElementById('nativeCheckBtn');  // 可能为 null（按钮已删除）
        this.nativeDeviceInfo = document.getElementById('nativeDeviceInfo');
        this.i2cStatusDot    = document.getElementById('i2cStatusDot');
        this.i2cStatusText   = document.getElementById('i2cStatusText');
        this.ddcciStatusDot  = document.getElementById('ddcciStatusDot');   // DDC/CI 支持状态
        this.ddcciStatusText = document.getElementById('ddcciStatusText');  // DDC/CI 文字
        this.i2cCmdLog       = document.getElementById('i2cCmdLog');
        this.exitBtn         = document.getElementById('exitBtn');
        this.displayTypeSel  = document.getElementById('displayType');
        this.ollamaUrlInput = document.getElementById('ollamaUrlInput');
        this.modelNameInput  = document.getElementById('modelNameInput');
        this.sensevoiceUrlInput = document.getElementById('sensevoiceUrlInput');
        // adbSection 已移除
        this.nativeSection   = document.getElementById('nativeSection');

        // Ollama URL + 模型名称输入 — 实时生效
        if (this.ollamaUrlInput) {
            this.ollamaUrlInput.addEventListener('change', () => this._applyOllamaUrl());
        }
        if (this.modelNameInput) {
            this.modelNameInput.addEventListener('change', () => this._applyOllamaUrl());
        }
        if (this.sensevoiceUrlInput) {
            this.sensevoiceUrlInput.addEventListener('change', () => this._applySensevoiceUrl());
        }

        // 显示器类型切换
        if (this.displayTypeSel) {
            this.displayTypeSel.addEventListener('change', (e) => {
                this.displayType = e.target.value;
                this._updateDisplayTypeUI();
                this._initDisplayController();
                this.addDebugLog(`切换显示器类型: ${this.displayType === 'adb' ? '外置屏幕' : '内置屏幕'}`);
            });
        }

        // 同步 displayType（构造函数里是硬编码默认值，要以 HTML selected 为准）
        if (this.displayTypeSel) {
            this.displayType = this.displayTypeSel.value;
        }

        // 初始化当前类型的控制器
        this._initDisplayController();

        // 退出按钮
        if (this.exitBtn) {
            this.exitBtn.addEventListener('click', () => {
                if (confirm('确定退出？')) {
                    navigator.sendBeacon('/exit');
                    window.close();
                }
            });
        }

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
                if (this.displayType === 'native') return; // 内置屏幕不支持对比度，静默忽略
                const val = parseInt(this.contrastSlider.value);
                this.executeI2cCommand('contrast', val);
            });
        }

        // 音量滑块（系统音量，走 native-display-api）
        if (this.volumeSlider) {
            this.volumeSlider.addEventListener('input', () => {
                const val = parseInt(this.volumeSlider.value);
                this.volumeValue.textContent = val;
            });
            this.volumeSlider.addEventListener('change', () => {
                const val = parseInt(this.volumeSlider.value);
                this._executeVolumeCommand(val);
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
                } else if (action === 'volume') {
                    this.volumeSlider.value = value;
                    this.volumeValue.textContent = value;
                    this._executeVolumeCommand(value);
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
        if (this.displayType === 'native') {
            // 内置屏幕禁用对比度
            this._setContrastControlsEnabled(false);
        } else {
            // 外置屏幕对比度是否可用由 DDC/CI 检测后决定，此处先启用
            this._setContrastControlsEnabled(true);
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
            this._updateDisplayTypeUI();
            // 外置屏幕通过 DDC/CI 检测
            setTimeout(() => this._checkDdcciSupport(), 100);
        }
        // 启动时读取系统音量同步滑块
        setTimeout(() => this._syncVolumeSlider(), 1200);
    }

    /** 读取系统音量并同步滑块/数字栏 */
    async _syncVolumeSlider() {
        if (!this.nativeDisplay) {
            this.nativeDisplay = new window.NativeDisplayClient();
        }
        try {
            const vol = await this.nativeDisplay.getVolume();
            if (vol != null) {
                if (this.volumeSlider) this.volumeSlider.value = vol;
                if (this.volumeValue) this.volumeValue.textContent = vol;
            }
        } catch (e) {
            this.addDebugLog(`[Volume] 读取音量失败: ${e.message}`);
        }
    }

    /**
     * 检测当前显示器是否支持 DDC/CI
     * 外置屏幕通过 dxva2.dll /ddcci/status 检测；内置屏幕标记为不适用
     */
    async _checkDdcciSupport() {
        const dot = this.ddcciStatusDot;
        const txt = this.ddcciStatusText;
        if (!dot || !txt) return;

        // 重置状态
        dot.className = 'status-dot status-dot-busy';
        txt.textContent = '检测中...';

        if (this.displayType === 'native') {
            // 内置屏幕走 WMI/gamma ramp，不依赖 DDC/CI 协议
            dot.className = 'status-dot status-dot-off';
            txt.textContent = 'DDC/CI 不适用';
            this.addDebugLog('[DDC/CI] 内置屏幕使用 WMI/Gamma Ramp，无需 DDC/CI');
            return;
        }

        // 外置屏幕 — 通过 /ddcci/status 检测 dxva2.dll 物理显示器可用性
        if (!this.ddcci) {
            this.ddcci = new window.DdcciClient();
        }
        try {
            const result = await this.ddcci.checkStatus();
            if (result.supported) {
                dot.className = 'status-dot status-dot-on';
                txt.textContent = 'DDC/CI 支持';
                this.addDebugLog(`[DDC/CI] ✓ 支持 (${result.manufacturerId || result.detail || 'OK'})`);
                // 同时更新 i2cStatusDot（外置屏幕已连接）
                if (this.i2cStatusDot) this.i2cStatusDot.className = 'status-dot status-dot-on';
                if (this.i2cStatusText) this.i2cStatusText.textContent = '已连接';
                // 启用对比度调节
                this._setContrastControlsEnabled(true);
                // 读取对比度当前值填充数字栏
                this._readDdcciContrast();
            } else if (result.connected) {
                dot.className = 'status-dot status-dot-off';
                txt.textContent = 'DDC/CI 无响应';
                this.addDebugLog(`[DDC/CI] ✗ 已连接但无响应: ${result.reason || ''}`);
                // 对比度不可用
                this._setContrastControlsEnabled(false);
            } else {
                // 详细区分错误原因
                const reason = result.reason || result.error || '';
                const isRouteMissing = reason.includes('non-JSON') || reason.includes('404') || reason.includes('DOCTYPE');
                if (isRouteMissing) {
                    dot.className = 'status-dot status-dot-off';
                    txt.textContent = '服务未重启';
                    this.addDebugLog(`[DDC/CI] ✗ /ddcci/ 路由可能未加载！请重启 server.py。详情: ${reason}`);
                } else {
                    dot.className = 'status-dot status-dot-off';
                    txt.textContent = 'DDC/CI 不可用';
                    this.addDebugLog(`[DDC/CI] ✗ 不可用: ${reason}`);
                }
                // 对比度不可用
                this._setContrastControlsEnabled(false);
            }
        } catch (e) {
            dot.className = 'status-dot status-dot-off';
            txt.textContent = 'DDC/CI 错误';
            this.addDebugLog(`[DDC/CI] ? 异常: ${e.message}`);
        }
    }

    /** 读取外置屏幕对比度当前值，填充数字栏 */
    async _readDdcciContrast() {
        if (!this.ddcci) {
            this.ddcci = new window.DdcciClient();
        }
        try {
            const result = await this.ddcci.getContrast();
            if (result && result.success && result.contrast != null) {
                if (this.contrastValue) {
                    this.contrastValue.textContent = result.contrast;
                }
                if (this.contrastSlider) {
                    this.contrastSlider.value = result.contrast;
                }
            }
        } catch (e) {
            this.addDebugLog(`[DDC/CI] 读取对比度失败: ${e.message}`);
        }
    }

    /** 启用/禁用对比度控件（根据 DDC/CI 支持状态） */
    _setContrastControlsEnabled(enabled) {
        if (this.contrastSlider) {
            this.contrastSlider.disabled = !enabled;
            this.contrastSlider.style.opacity = enabled ? '1' : '0.4';
            this.contrastSlider.title = enabled ? '' : '此显示器不支持对比度调节';
        }
        if (this.contrastValue) {
            if (enabled) {
                this.contrastValue.style.color = '';
            } else {
                this.contrastValue.textContent = '—';
                this.contrastValue.style.color = '#8e8e93';
            }
        }
    }

    async checkAdbConnection() {
        // 按钮可能已删除（顶部已有连接状态），仅更新信息文本
        if (this.adbCheckBtn) {
            this.adbCheckBtn.disabled = true;
            this.adbCheckBtn.textContent = '检测中...';
        }
        try {
            const result = await this.i2c.checkConnection();
            if (result.connected) {
                if (this.adbDeviceInfo) this.adbDeviceInfo.textContent = `✅ ${result.deviceCount} 台设备`;
                this.addDebugLog(`外置屏幕已连接: ${result.devices.join(', ')}`);
            } else {
                if (this.adbDeviceInfo) this.adbDeviceInfo.textContent = `❌ ${result.error || '无设备'}`;
                this.addDebugLog(`外置屏幕未连接: ${result.error || '无设备'}`);
            }
        } catch (e) {
            if (this.adbDeviceInfo) this.adbDeviceInfo.textContent = `❌ ${e.message}`;
            this.addDebugLog(`外置屏幕检测异常: ${e.message}`);
        } finally {
            if (this.adbCheckBtn) {
                this.adbCheckBtn.disabled = false;
                this.adbCheckBtn.textContent = '检测设备';
            }
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
        this.addDebugLog(`[Display] set ${controlName}=${value} displayType=${this.displayType}`);

        // colorTemp: ADB显示器走DDC/CI VCP 0x0B，内置屏幕走gamma ramp
        if (controlName === 'colorTemp') {
            if (this.displayType === 'adb') {
                this.addDebugLog('[ColorTemp] → ADB DDC/CI path');
                await this._executeAdbCommand(controlName, value);
            } else {
                this.addDebugLog('[ColorTemp] → Gamma ramp path');
                await this._executeGammaCommand(controlName, value);
            }
            return;
        }

        // gamma: 仅内置屏幕支持，ADB显示器不支持（无标准DDC/CI gamma命令）
        if (controlName === 'gamma') {
            if (this.displayType === 'native') {
                await this._executeGammaCommand(controlName, value);
            } else {
                this.appendI2cLog('伽马调节仅支持内置屏幕', true);
                this.updateI2cStatus('error');
            }
            return;
        }

        // volume: 系统音量，不依赖显示器类型
        if (controlName === 'volume') {
            await this._executeVolumeCommand(value);
            return;
        }

        if (this.displayType === 'native') {
            await this._executeNativeCommand(controlName, value);
        } else {
            await this._executeAdbCommand(controlName, value);
        }
    }

    async _executeGammaCommand(controlName, value) {
        if (!this.nativeDisplay) {
            this.nativeDisplay = new window.NativeDisplayClient();
        }
        try {
            let result;
            if (controlName === 'colorTemp') {
                result = await this.nativeDisplay.setColorTemp(value);
            } else if (controlName === 'gamma') {
                result = await this.nativeDisplay.setGamma(value);
            } else {
                return;
            }
            if (result.success) {
                this.addDebugLog(`[Gamma] ok ${controlName}=${value}`);
                this.updateI2cStatus('connected');
            } else {
                this.addDebugLog(`[Gamma] fail: ${result.error}`);
                this.appendI2cLog(`错误: ${result.error}`, true);
                this.updateI2cStatus('error');
            }
        } catch (e) {
            this.addDebugLog(`[Gamma] exception: ${e.message}`);
            this.appendI2cLog(`异常: ${e.message}`, true);
            this.updateI2cStatus('error');
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
                // 内置屏幕不支持对比度（DDC/CI 对比度需要显示器硬件支持，通常不可用）
                this.appendI2cLog(`[Native] 对比度=—（内置屏幕不支持）`);
                this.updateI2cStatus('connected');
                return;
            } else if (controlName === 'colorTemp') {
                result = await this.nativeDisplay.setColorTemp(value);
                this.appendI2cLog(`[Native] 色温=${value}`);
            } else {
                this.updateI2cStatus('error');
                return;
            }

            if (result.success) {
                this.addDebugLog(`[Native] ✓ ${controlName}=${value} 成功`);
                this.updateI2cStatus(this.nativeDisplay.connected ? 'connected' : 'disconnected');
                // 亮度设置后回读确认（WMI 可能静默失败）
                if (controlName === 'brightness') {
                    const current = await this.nativeDisplay.getBrightness();
                    if (current != null) {
                        const actual = Math.round(current);
                        this.brightnessSlider.value = actual;
                        this.brightnessValue.textContent = actual;
                        this.addDebugLog(`[Native] 回读确认: 实际亮度=${actual}%`);
                    }
                }
            } else {
                this.addDebugLog(`[Native] ✗ 失败: ${result.error}`);
                this.appendI2cLog(`错误: ${result.error}`, true);
                this.updateI2cStatus('error');
            }
        } catch (e) {
            this.addDebugLog(`[Native] ✗ 异常: ${e.message}`);
            this.appendI2cLog(`异常: ${e.message}`, true);
            this.updateI2cStatus('error');
        }
    }

    /**
     * 外置屏幕亮度/对比度：通过 DDC/CI (dxva2.dll) 控制
     * VCP 0x10 = 亮度, VCP 0x12 = 对比度，范围均为 0-100
     */
    async _executeDdcciVcp(controlName, value) {
        if (!this.ddcci) {
            this.ddcci = new window.DdcciClient();
        }
        this.updateI2cStatus('executing');
        const vcpMap = { brightness: '0x10', contrast: '0x12' };
        this.addDebugLog(`[DDC/CI] set ${controlName}=${value}% (VCP ${vcpMap[controlName] || '?'})`);
        try {
            let result;
            if (controlName === 'brightness') {
                result = await this.ddcci.setBrightness(value);
            } else if (controlName === 'contrast') {
                result = await this.ddcci.setContrast(value);
            }
            if (result && result.success) {
                this.addDebugLog(`[DDC/CI] ✓ ${controlName}=${value} 成功`);
                this.updateI2cStatus('connected');
                this.appendI2cLog(`[DDC/CI] ${controlName}=${value}%`);
            } else {
                const err = (result && result.error) ? result.error : '未知错误';
                this.addDebugLog(`[DDC/CI] ✗ 失败: ${err}`);
                this.appendI2cLog(`错误: ${err}`, true);
                this.updateI2cStatus('error');
            }
        } catch (e) {
            this.addDebugLog(`[DDC/CI] ✗ 异常: ${e.message}`);
            this.appendI2cLog(`异常: ${e.message}`, true);
            this.updateI2cStatus('error');
        }
    }

    async _executeAdbCommand(controlName, value) {
        // ── 外置屏幕亮度/对比度：走 DDC/CI dxva2.dll（而非 ADB i2cset）──
        if ((controlName === 'brightness' || controlName === 'contrast') && this.displayType === 'adb') {
            await this._executeDdcciVcp(controlName, value);
            return;
        }

        if (!this.i2c) return;

        // 色温：ADB 显示器尝试 DDC/CI VCP 0x0B（部分显示器支持）
        if (controlName === 'colorTemp') {
            await this._executeAdbDdcCi(controlName, value);
            return;
        }

        try {
            const result = await this.i2c.setControl(controlName, value);
            // setControl 内部已构建命令，直接用 lastCommand 写日志，避免重复构建
            if (this.i2c.lastCommand) {
                this.appendI2cLog(this.i2c.lastCommand.cmdStr);
            }
            this.addDebugLog(`[ADB] ✓ ${controlName}=${value} 成功`);
            this.updateI2cStatus(this.i2c.connected ? 'connected' : 'disconnected');
        } catch (e) {
            this.addDebugLog(`[ADB] ✗ 失败: ${e.message}`);
            this.appendI2cLog(`错误: ${e.message}`, true);
            this.updateI2cStatus('error');
        }
    }

    async _executeAdbDdcCi(controlName, value) {
        const vcpCode = I2C_CONFIG.VCP_CODES[controlName] || 0x10;
        const { bytes, cmdStr, toHex } = buildDdcCiCommand(vcpCode, value);
        this.appendI2cLog(`[DDC/CI] ${cmdStr}`);
        try {
            const resp = await fetch(`${I2C_CONFIG.apiPrefix}/i2cset`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    command: 'i2cset',
                    args: ['-y', '-f', String(I2C_CONFIG.bus),
                        ...bytes.map(b => '0x' + toHex(b)), 'i'],
                }),
            });
            const result = await resp.json();
            if (result.success) {
                this.addDebugLog(`[DDC/CI] ok ${controlName}=${value}`);
                this.updateI2cStatus('connected');
            } else {
                this.addDebugLog(`[DDC/CI] fail: ${result.error}`);
                this.appendI2cLog(`错误: ${result.error}`, true);
                this.updateI2cStatus('error');
            }
        } catch (e) {
            this.addDebugLog(`[DDC/CI] exception: ${e.message}`);
            this.appendI2cLog(`异常: ${e.message}`, true);
            this.updateI2cStatus('error');
        }
    }

    /** 设置系统音量 */
    async _executeVolumeCommand(value) {
        if (!this.nativeDisplay) {
            this.nativeDisplay = new window.NativeDisplayClient();
        }
        try {
            const result = await this.nativeDisplay.setVolume(value);
            if (result.success) {
                this.addDebugLog(`[Volume] ✓ 音量=${value}%`);
                this.updateI2cStatus('connected');
                this.appendI2cLog(`[音量] ${value}%`);
            } else {
                this.addDebugLog(`[Volume] ✗ 失败: ${result.error}`);
                this.appendI2cLog(`错误: ${result.error}`, true);
                this.updateI2cStatus('error');
            }
        } catch (e) {
            this.addDebugLog(`[Volume] ✗ 异常: ${e.message}`);
            this.appendI2cLog(`异常: ${e.message}`, true);
            this.updateI2cStatus('error');
        }
    }

    async checkNativeConnection() {
        // 按钮可能已删除（顶部已有连接状态），仅更新信息文本
        if (this.nativeCheckBtn) {
            this.nativeCheckBtn.disabled = true;
            this.nativeCheckBtn.textContent = '检测中...';
        }
        try {
            if (!this.nativeDisplay) {
                this.nativeDisplay = new window.NativeDisplayClient();
            }
            const result = await this.nativeDisplay.checkConnection();
            if (result.connected) {
                if (this.nativeDeviceInfo) this.nativeDeviceInfo.textContent = `✅ 已连接`;
                this.addDebugLog(`内置屏幕已连接 (亮度 ${result.brightness}%)`);
                this.updateI2cStatus('connected');
                // 用检测到的当前亮度更新滑块
                if (result.brightness != null) {
                    this.brightnessSlider.value = result.brightness;
                    this.brightnessValue.textContent = result.brightness;
                }
                // 读取当前系统音量并同步滑块
                const vol = await this.nativeDisplay.getVolume();
                if (vol != null && this.volumeSlider) {
                    this.volumeSlider.value = vol;
                    this.volumeValue.textContent = vol;
                }
            } else {
                if (this.nativeDeviceInfo) this.nativeDeviceInfo.textContent = `❌ ${result.error || '不可用'}`;
                this.addDebugLog(`内置屏幕不可用: ${result.error}`);
                this.updateI2cStatus('disconnected');
            }
        } catch (e) {
            if (this.nativeDeviceInfo) this.nativeDeviceInfo.textContent = `❌ ${e.message}`;
            this.addDebugLog(`内置屏幕检测异常: ${e.message}`);
            this.updateI2cStatus('disconnected');
        } finally {
            if (this.nativeCheckBtn) {
                this.nativeCheckBtn.disabled = false;
                this.nativeCheckBtn.textContent = '检测连接';
            }
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

        // 内置屏幕不支持电源控制和对比度（WMI 无此接口）
        if (this.displayType === 'native' && intent.control === 'powerMode') {
            return null; // 静默忽略
        }
        if (this.displayType === 'native' && intent.control === 'contrast') {
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

            // 亮度/对比度/色温 0-100 范围的控制 — 更新滑块 UI
            if (intent.control === 'brightness' && this.brightnessSlider) {
                this.brightnessSlider.value = targetVal;
                this.brightnessValue.textContent = targetVal;
            } else if (intent.control === 'contrast' && this.contrastSlider) {
                this.contrastSlider.value = targetVal;
                this.contrastValue.textContent = targetVal;
            } else if (intent.control === 'colorTemp' && this.colorTempSlider) {
                this.colorTempSlider.value = targetVal;
                this.colorTempValue.textContent = targetVal;
            } else if (intent.control === 'gamma' && this.gammaSlider) {
                this.gammaSlider.value = targetVal;
                this.gammaValue.textContent = targetVal;
            } else if (intent.control === 'volume' && this.volumeSlider) {
                this.volumeSlider.value = targetVal;
                this.volumeValue.textContent = targetVal;
            }

            this.addDebugLog(`[I2C] 🖥️ [${intent.control}] → ${targetVal}%，已同步滑块`);
            // 非阻塞执行 i2cset（fire-and-forget）
            this.executeI2cCommand(intent.control, targetVal);

        } else if (intent.action === 'adjust') {
            let slider;
            if (intent.control === 'brightness') slider = this.brightnessSlider;
            else if (intent.control === 'contrast') slider = this.contrastSlider;
            else if (intent.control === 'colorTemp') slider = this.colorTempSlider;
            else if (intent.control === 'gamma') slider = this.gammaSlider;
            else if (intent.control === 'volume') slider = this.volumeSlider;
            if (!slider) return intent;

            let current = parseInt(slider.value) ?? 50;
            let delta = intent.delta;
            let targetVal = current + delta;
            // 边界处理：调低时 current<=10 直接到0，调高时 current>=90 直接到100
            if (intent.control === 'volume' || intent.control === 'brightness' || intent.control === 'contrast') {
                if (delta < 0 && current <= 10) {
                    targetVal = 0;
                } else if (delta > 0 && current >= 90) {
                    targetVal = 100;
                }
            }
            targetVal = Math.max(0, Math.min(100, targetVal));

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
            } else if (intent.control === 'colorTemp' && this.colorTempValue) {
                this.colorTempValue.textContent = targetVal;
            } else if (intent.control === 'gamma' && this.gammaValue) {
                this.gammaValue.textContent = targetVal;
            } else if (intent.control === 'volume' && this.volumeValue) {
                this.volumeValue.textContent = targetVal;
            }

            this.addDebugLog(`[I2C] 🖥️ [${intent.control}] ${direction} ${targetVal}，已同步滑块`);
            this.executeI2cCommand(intent.control, targetVal);
        }

        return intent;
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
