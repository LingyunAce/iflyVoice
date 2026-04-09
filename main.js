class SpeechRecognitionApp {
    constructor() {
        this.recognition = null;
        this.iflytekRecognizer = null;
        this.isRecording = false;
        this.recordBtn = document.getElementById('recordBtn');
        this.statusEl = document.getElementById('status');
        this.resultEl = document.getElementById('result');
        this.debugLogEl = document.getElementById('debugLog');
        this.apiSelector = document.querySelectorAll('input[name="apiType"]');
        this.iflytekConfigDiv = document.getElementById('iflytekConfig');
        this.deviceSelectorEl = document.getElementById('deviceSelector'); // 设备选择器
        
        this.maxRecordTime = 30000; // 最长录制时间（30秒）
        this.recordTimer = null; // 录制计时器
        
        this.recognizedText = ''; // 累积识别的文本
        this.currentApi = 'browser'; // 当前使用的API: 'browser' 或 'iflytek'
        this.debugLogs = [];
        this.selectedDeviceId = null; // 用户选择的音频输入设备ID
        this.init();
    }
    
    init() {
        this.initApiSelector();
        this.initSpeechRecognition();
        this.bindEvents();
        this.checkBrowserSupport();
        // 枚举并填充设备列表
        this.loadAudioDevices();
    }
    
    initApiSelector() {
        this.apiSelector.forEach(radio => {
            radio.addEventListener('change', (e) => {
                this.currentApi = e.target.value;
                this.addDebugLog(`切换到 ${this.currentApi === 'iflytek' ? '讯飞' : '浏览器内置'} API`);
                
                if (this.currentApi === 'iflytek') {
                    this.iflytekConfigDiv.style.display = 'block';
                } else {
                    this.iflytekConfigDiv.style.display = 'none';
                }
            });
        });
    }
    
    // 枚举音频输入设备，填充选择器
    async loadAudioDevices() {
        // 如果HTML里没有 deviceSelector 元素，动态创建并插入到讯飞配置区域
        if (!this.deviceSelectorEl) {
            const iflytekDiv = this.iflytekConfigDiv;
            if (!iflytekDiv) return;

            const wrapper = document.createElement('div');
            wrapper.style.cssText = 'margin: 10px 0; display: flex; flex-direction: column; gap: 6px;';

            const label = document.createElement('label');
            label.textContent = '🎤 选择麦克风设备（耳机/Headset）：';
            label.style.cssText = 'font-size: 13px; font-weight: 600; color: #e0e0e0;';

            const select = document.createElement('select');
            select.id = 'deviceSelector';
            select.style.cssText = [
                'padding: 8px 12px',
                'border-radius: 8px',
                'border: 1px solid rgba(255,255,255,0.2)',
                'background: rgba(255,255,255,0.08)',
                'color: #fff',
                'font-size: 13px',
                'cursor: pointer',
                'outline: none',
                'max-width: 100%',
            ].join(';');

            const hint = document.createElement('p');
            hint.style.cssText = 'font-size: 11px; color: rgba(255,255,255,0.45); margin: 0;';
            hint.textContent = '⚠ 若默认麦克风走 Realtek 通道，请在此选择耳机/蓝牙麦克风对应条目';

            wrapper.appendChild(label);
            wrapper.appendChild(select);
            wrapper.appendChild(hint);
            iflytekDiv.insertBefore(wrapper, iflytekDiv.firstChild);
            this.deviceSelectorEl = select;
        }

        try {
            const devices = await enumerateAudioInputDevices();
            this.deviceSelectorEl.innerHTML = '<option value="">默认麦克风（系统默认）</option>';
            devices.forEach(d => {
                const opt = document.createElement('option');
                opt.value = d.deviceId;
                opt.textContent = d.label;
                this.deviceSelectorEl.appendChild(opt);
            });
            this.addDebugLog(`找到 ${devices.length} 个音频输入设备`);
            devices.forEach((d, i) => {
                this.addDebugLog(`  设备${i+1}: ${d.label} (${d.deviceId.slice(0,16)}...)`);
            });
            
            // 监听选择变化
            this.deviceSelectorEl.addEventListener('change', (e) => {
                this.selectedDeviceId = e.target.value || null;
                const label = e.target.options[e.target.selectedIndex].text;
                this.addDebugLog(`✓ 已切换麦克风: ${label}`);
            });
        } catch (err) {
            this.addDebugLog(`枚举设备失败: ${err.message}`);
        }
    }
    
    checkBrowserSupport() {
        if (!this.recognition) {
            this.showError('您的浏览器不支持语音识别功能，请使用Chrome、Edge或Safari浏览器');
            this.recordBtn.disabled = true;
        }
    }
    
    initSpeechRecognition() {
        const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
        
        if (SpeechRecognition) {
            this.recognition = new SpeechRecognition();
            this.recognition.continuous = true; // 持续识别，不会自动中断
            this.recognition.interimResults = true; // 显示中间结果
            this.recognition.lang = 'zh-CN'; // 设置为中文识别
            this.recognition.maxAlternatives = 1; // 返回一个识别结果
            
            this.recognition.onstart = () => {
                this.isRecording = true;
                this.updateUI();
                this.updateStatus('正在录音...', true);
                this.addDebugLog('语音识别已启动 (onstart)');
            };
            
            this.recognition.onresult = (event) => {
                // 累积所有识别结果
                let finalText = '';
                for (let i = 0; i < event.results.length; i++) {
                    finalText += event.results[i][0].transcript;
                }
                
                // 保存累积的文本
                this.recognizedText = finalText;
                
                const transcript = event.results[event.results.length - 1][0].transcript;
                const confidence = event.results[event.results.length - 1][0].confidence;
                const isFinal = event.results[event.results.length - 1].isFinal;
                
                if (isFinal) {
                    this.displayResult(this.recognizedText);
                    this.addDebugLog(`最终识别结果: ${transcript} (置信度: ${(confidence * 100).toFixed(1)}%)`);
                } else {
                    // 实时显示中间结果
                    this.displayResult(this.recognizedText);
                    this.addDebugLog(`临时识别结果: ${transcript} (置信度: ${(confidence * 100).toFixed(1)}%)`);
                }
            };
            
            this.recognition.onerror = (event) => {
                this.addDebugLog(`识别错误: ${event.error} - ${event.message || ''}`);
                this.handleError(event.error);
            };
            
            this.recognition.onend = () => {
                this.isRecording = false;
                this.updateUI();
                this.updateStatus('准备就绪');
                this.addDebugLog('语音识别已结束 (onend) - 原因: 用户停止或自动中断');
                
                // 清除计时器
                if (this.recordTimer) {
                    clearTimeout(this.recordTimer);
                    this.recordTimer = null;
                }
            };
            
            // 添加更多事件监听来诊断问题
            this.recognition.onnomatch = (event) => {
                this.addDebugLog('警告: 未识别到匹配的语音 (onnomatch)');
            };
            
            this.recognition.onsoundstart = () => {
                this.addDebugLog('检测到声音 (onsoundstart)');
            };
            
            this.recognition.onsoundend = () => {
                this.addDebugLog('声音结束 (onsoundend)');
            };
            
            this.recognition.onspeechstart = () => {
                this.addDebugLog('检测到语音 (onspeechstart)');
            };
            
            this.recognition.onspeechend = () => {
                this.addDebugLog('语音结束 (onspeechend)');
                // 当检测到语音结束时，自动停止（用户不需要手动停止）
                setTimeout(() => {
                    if (this.isRecording) {
                        this.addDebugLog('语音结束5秒后自动停止录音');
                        this.stopRecording();
                    }
                }, 5000);
            };
            
            this.recognition.onaudiostart = () => {
                this.addDebugLog('音频捕获开始 (onaudiostart)');
            };
            
            this.recognition.onaudioend = () => {
                this.addDebugLog('音频捕获结束 (onaudioend)');
            };
            
            this.addDebugLog('语音识别API初始化成功');
            this.addDebugLog(`浏览器: ${navigator.userAgent}`);
            this.addDebugLog(`语言设置: zh-CN`);
            this.addDebugLog('配置: continuous=true, interimResults=true');
        } else {
            this.addDebugLog('错误: 浏览器不支持SpeechRecognition API');
        }
    }
    
    bindEvents() {
        // 统一点击事件（支持鼠标和触摸）
        this.recordBtn.addEventListener('click', async (e) => {
            await this.handleClick();
        });
        
        // 防止右键菜单
        this.recordBtn.addEventListener('contextmenu', (e) => {
            e.preventDefault();
        });
    }
    
    async handleClick() {
        // 切换录音状态
        if (this.isRecording) {
            await this.stopRecording();
        } else {
            await this.startRecording();
        }
    }
    
    async startRecording() {
        if (this.isRecording) {
            this.addDebugLog('错误: 已经在录音中');
            return;
        }
        
        // 清空之前的识别结果
        this.recognizedText = '';
        this.resultEl.innerHTML = '<div class="placeholder">正在识别中...</div>';
        this.resultEl.classList.remove('success');
        
        try {
            if (this.currentApi === 'browser') {
                // 使用浏览器内置API
                if (!this.recognition) {
                    this.addDebugLog('错误: 浏览器不支持语音识别');
                    return;
                }
                
                this.recognition.start();
                this.addDebugLog('开始录音 (浏览器API)...');
                
            } else if (this.currentApi === 'iflytek') {
                // 使用讯飞API
                if (!window.IflytekSpeechRecognizer) {
                    this.addDebugLog('错误: 讯飞API模块未加载');
                    return;
                }
                
                try {
                    // 初始化讯飞识别器
                    this.iflytekRecognizer = new window.IflytekSpeechRecognizer({
                        appId: IFLYTEK_CONFIG.APPID,
                        apiKey: IFLYTEK_CONFIG.APIKey,
                        apiSecret: IFLYTEK_CONFIG.APISecret,
                        deviceId: this.selectedDeviceId, // 传入用户选择的设备ID
                        onResult: (result) => {
                            this.recognizedText = result.text;
                            this.displayResult(result.text);
                            this.addDebugLog(`讯飞识别结果: ${result.text} ${result.isFinal ? '(最终)' : '(临时)'}`);
                        },
                        onError: (error) => {
                            this.addDebugLog(`讯飞API错误: ${error.message}`);
                            this.showError(error.message);
                        },
                        onStatusChange: (status) => {
                            this.addDebugLog(`讯飞状态: ${status}`);
                        }
                    });
                    
                    // 绑定调试日志
                    this.iflytekRecognizer.addDebugLog = (msg) => {
                        this.addDebugLog(`[讯飞] ${msg}`);
                    };
                    
                    await this.iflytekRecognizer.start();
                    this.addDebugLog('开始录音 (讯飞API)...');
                    
                } catch (error) {
                    this.addDebugLog(`启动讯飞API失败: ${error.message}`);
                    this.showError(`讯飞API配置错误: ${error.message}`);
                    return;
                }
            }
            
            this.isRecording = true;
            this.updateUI();
            
            // 设置30秒自动停止
            this.recordTimer = setTimeout(() => {
                if (this.isRecording) {
                    this.addDebugLog('30秒时间到，自动停止录音');
                    this.stopRecording();
                    this.showTemporaryMessage('已达到最长录制时间（30秒）');
                }
            }, this.maxRecordTime);
            
        } catch (error) {
            this.addDebugLog(`启动录音失败: ${error.message || error}`);
            this.handleError(error);
        }
    }
    
    async stopRecording() {
        if (!this.isRecording) return;
        
        this.addDebugLog('停止录音...');
        
        // 清除自动停止计时器
        if (this.recordTimer) {
            clearTimeout(this.recordTimer);
            this.recordTimer = null;
            this.addDebugLog('清除自动停止计时器');
        }
        
        try {
            if (this.currentApi === 'browser' && this.recognition) {
                // 显示当前累积的识别结果
                if (this.recognizedText && this.recognizedText.trim()) {
                    this.displayResult(this.recognizedText);
                    this.addDebugLog(`手动停止，当前识别结果: ${this.recognizedText}`);
                }
                
                this.recognition.stop();
                
            } else if (this.currentApi === 'iflytek' && this.iflytekRecognizer) {
                // 停止讯飞识别
                // 注意：stop() 是异步流程（先发结束帧，等讯飞返回最终结果）
                // 最终文本已通过 onResult(isFinal=true) 回调实时更新到界面，这里不再重复设置
                // 只在确实有已识别内容但 onResult 还没触发最终帧时，保留已有显示
                this.iflytekRecognizer.stop();
                this.addDebugLog(`讯飞识别停止，等待最终结果回调...`);
                
                // 如果已经有累积结果，确保显示（防止 onResult 在 stop 前就完成了）
                if (this.recognizedText && this.recognizedText.trim()) {
                    this.displayResult(this.recognizedText);
                }
                
                this.iflytekRecognizer = null;
            }
            
            this.isRecording = false;
            this.updateUI();
            
        } catch (error) {
            this.addDebugLog(`停止录音出错: ${error.message}`);
            this.showError(`停止失败: ${error.message}`);
        }
    }
    
    updateUI() {
        const btnText = this.recordBtn.querySelector('.btn-text');
        if (this.isRecording) {
            this.recordBtn.classList.add('recording');
            this.statusEl.classList.add('recording');
            if (btnText) {
                btnText.textContent = '停止录音';
            }
        } else {
            this.recordBtn.classList.remove('recording');
            this.statusEl.classList.remove('recording');
            if (btnText) {
                btnText.textContent = '开始录音';
            }
        }
    }
    
    updateStatus(text, isRecording = false) {
        this.statusEl.textContent = text;
        if (isRecording) {
            this.statusEl.classList.add('recording');
        }
    }
    
    displayResult(text) {
        this.resultEl.innerHTML = `<div class="result-text">${text}</div>`;
        this.resultEl.classList.add('success');
    }
    
    showError(message) {
        this.resultEl.innerHTML = `<div class="error">${message}</div>`;
    }
    
    showTemporaryMessage(message) {
        const originalStatus = this.statusEl.textContent;
        this.updateStatus(message);
        
        setTimeout(() => {
            this.updateStatus(originalStatus);
        }, 2000);
    }
    
    handleError(error) {
        let errorMessage = '';
        
        switch (error) {
            case 'no-speech':
                errorMessage = '未检测到语音，请重试';
                break;
            case 'audio-capture':
                errorMessage = '无法访问麦克风，请检查权限设置';
                break;
            case 'not-allowed':
                errorMessage = '麦克风权限被拒绝，请在浏览器设置中允许访问';
                break;
            case 'network':
                errorMessage = '网络错误，请检查网络连接';
                break;
            case 'aborted':
                errorMessage = '识别已中断';
                break;
            default:
                errorMessage = '识别出错：' + error;
        }
        
        this.addDebugLog(`错误信息: ${errorMessage}`);
        this.showError(errorMessage);
    }
    
    addDebugLog(message) {
        const timestamp = new Date().toLocaleTimeString();
        const logEntry = `[${timestamp}] ${message}`;
        
        this.debugLogs.push(logEntry);
        
        // 限制日志数量，保留最近50条
        if (this.debugLogs.length > 50) {
            this.debugLogs = this.debugLogs.slice(-50);
        }
        
        this.updateDebugLog();
    }
    
    updateDebugLog() {
        if (this.debugLogEl) {
            this.debugLogEl.textContent = this.debugLogs.join('\n');
            // 自动滚动到底部
            this.debugLogEl.scrollTop = this.debugLogEl.scrollHeight;
        }
    }
}

// 初始化应用
document.addEventListener('DOMContentLoaded', () => {
    new SpeechRecognitionApp();
});

// 防止页面滚动
document.addEventListener('touchmove', function(e) {
    if (e.target.closest('.record-btn')) {
        e.preventDefault();
    }
}, { passive: false });