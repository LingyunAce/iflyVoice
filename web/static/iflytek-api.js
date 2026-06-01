// 讯飞语音识别API配置
const IFLYTEK_CONFIG = {
    APPID: 'f8a90305', // 用户提供的APPID（32位十六进制）
    APIKey: 'db47537dda15407be26c56c0cfd40689', // 需要用户填写（32位十六进制）
    APISecret: 'ZmFlNDkyYTYxNTQ1YjA4YTM3MmFjZGMy', // 需要用户填写（24位Base64）
    hostUrl: 'wss://iat-api.xfyun.cn/v2/iat',
    host: 'iat-api.xfyun.cn',
    uri: '/v2/iat'
};

// ===== 设备枚举工具 =====
// 枚举所有音频输入设备，返回 [{deviceId, label}] 列表
async function enumerateAudioInputDevices() {
    // 先申请一次权限，否则 label 会是空字符串
    try {
        const tempStream = await navigator.mediaDevices.getUserMedia({ audio: true });
        tempStream.getTracks().forEach(t => t.stop());
    } catch (_) { /* ignore */ }

    const devices = await navigator.mediaDevices.enumerateDevices();
    return devices
        .filter(d => d.kind === 'audioinput')
        .map(d => ({ deviceId: d.deviceId, label: d.label || `麦克风 (${d.deviceId.slice(0, 8)})` }));
}

// ===== PCM 重采样工具 =====
// 使用 OfflineAudioContext 将任意采样率的 Float32Array 重采样到 targetRate
async function resampleTo16k(inputFloat32, inputSampleRate) {
    if (inputSampleRate === 16000) return inputFloat32;

    const targetRate = 16000;
    const duration = inputFloat32.length / inputSampleRate;
    const outputLength = Math.ceil(duration * targetRate);

    const offlineCtx = new OfflineAudioContext(1, outputLength, targetRate);
    const audioBuffer = offlineCtx.createBuffer(1, inputFloat32.length, inputSampleRate);
    audioBuffer.copyToChannel(inputFloat32, 0);

    const source = offlineCtx.createBufferSource();
    source.buffer = audioBuffer;
    source.connect(offlineCtx.destination);
    source.start();

    const rendered = await offlineCtx.startRendering();
    return rendered.getChannelData(0);
}

// 生成讯飞的认证URL
function getWebSocketUrl() {
    const apiKey = IFLYTEK_CONFIG.APIKey;
    const apiSecret = IFLYTEK_CONFIG.APISecret;
    
    if (apiKey === 'YOUR_API_KEY_HERE' || apiSecret === 'YOUR_API_SECRET_HERE') {
        throw new Error('请先设置正确的 APIKey 和 APISecret');
    }
    
    // 检查APIKey格式
    if (apiKey.length !== 32) {
        console.warn(`警告：APIKey长度应为32位，当前为${apiKey.length}位`);
    }
    
    const host = IFLYTEK_CONFIG.host;
    const date = new Date().toGMTString();
    const algorithm = 'hmac-sha256';
    const headers = 'host date request-line';
    
    const signatureOrigin = `host: ${host}\ndate: ${date}\nGET ${IFLYTEK_CONFIG.uri} HTTP/1.1`;
    
    const signatureSha = CryptoJS.HmacSHA256(signatureOrigin, apiSecret);
    const signature = CryptoJS.enc.Base64.stringify(signatureSha);
    
    const authorizationOrigin = `api_key="${apiKey}", algorithm="${algorithm}", headers="${headers}", signature="${signature}"`;
    const authorization = btoa(authorizationOrigin);
    
    const url = `${IFLYTEK_CONFIG.hostUrl}?authorization=${authorization}&date=${encodeURIComponent(date)}&host=${host}`;
    
    console.log('生成的认证URL:', url.substring(0, 150) + '...');
    console.log('APIKey长度:', apiKey.length, '位');
    console.log('APPID:', IFLYTEK_CONFIG.APPID);
    
    return url;
}

// 讯飞语音识别API集成类
class IflytekSpeechRecognizer {
    constructor(options = {}) {
        this.appId = options.appId || IFLYTEK_CONFIG.APPID;
        this.apiKey = options.apiKey || IFLYTEK_CONFIG.APIKey;
        this.apiSecret = options.apiSecret || IFLYTEK_CONFIG.APISecret;
        // 指定麦克风设备ID（解决耳机通道不生效问题）
        this.deviceId = options.deviceId || null;
        
        this.ws = null;
        this.mediaRecorder = null;
        this.audioChunks = [];
        
        this.onResult = options.onResult || (() => {});
        this.onError = options.onError || (() => {});
        this.onStatusChange = options.onStatusChange || (() => {});
        
        this.isRecording = false;
        this.fullResult = '';
        // 用于 pgs 文本累积：confirmedResult=已终结段落，currentSegment=当前推测中的段落
        this.confirmedResult = '';
        this.currentSegment = '';
        this.sessionId = null;
        this.sessionValid = true;
        this.recognitionComplete = false;
    }
    
    // 开始录音和识别
    async start() {
        try {
            // 检查API配置
            if (this.apiKey === 'YOUR_API_KEY_HERE' || this.apiSecret === 'YOUR_API_SECRET_HERE') {
                throw new Error('讯飞API配置不完整，请设置APIKey和APISecret');
            }
            
            // ===== 关键修复：指定 deviceId 以使用选定的麦克风设备 =====
            // 不指定 deviceId 时，浏览器默认用系统默认麦克风（通常是 Realtek）
            // 注意：getUserMedia 的 sampleRate 约束只是"建议"，浏览器可忽略
            // 实际采样率以 AudioContext.sampleRate 为准，需要用重采样处理
            const audioConstraints = {
                channelCount: { ideal: 1 },
                echoCancellation: true,
                noiseSuppression: true,
                autoGainControl: true,
            };
            if (this.deviceId) {
                audioConstraints.deviceId = { exact: this.deviceId };
                this.addDebugLog(`使用指定设备ID: ${this.deviceId}`);
            } else {
                this.addDebugLog('未指定设备ID，使用系统默认麦克风');
            }

            const stream = await navigator.mediaDevices.getUserMedia({ audio: audioConstraints });
            
            // 检查麦克风轨道状态
            const audioTrack = stream.getAudioTracks()[0];
            this.addDebugLog(`麦克风轨道: ${audioTrack.label}, 状态: ${audioTrack.readyState}, 已静音: ${audioTrack.muted}`);
            
            // 添加轨道状态监听
            audioTrack.onmute = () => {
                this.addDebugLog('⚠ 警告：麦克风被静音');
            };
            audioTrack.onunmute = () => {
                this.addDebugLog('✓ 麦克风已解除静音');
            };
            audioTrack.onended = () => {
                this.addDebugLog('⚠ 警告：麦克风轨道已结束');
            };
            
            // 建立WebSocket连接
            await this.connectWebSocket();
            
            // 开始录制音频
            this.startRecording(stream);
            
            this.isRecording = true;
            this.fullResult = '';
            this.confirmedResult = '';
            this.currentSegment = '';
            this.sessionValid = true;
            this.recognitionComplete = false;
            this.sessionId = null;
            this.onStatusChange('recording');
            
        } catch (error) {
            this.onError(error);
            throw error;
        }
    }
    
    // 建立WebSocket连接
    connectWebSocket() {
        return new Promise((resolve, reject) => {
            try {
                const url = getWebSocketUrl();
                this.addDebugLog(`连接到讯飞API: ${url}`);
                
                this.ws = new WebSocket(url);
                
                this.ws.onopen = () => {
                    this.addDebugLog('WebSocket连接已建立');
                    
                    // 发送开始帧
                    const frame = {
                        common: {
                            app_id: this.appId
                        },
                        business: {
                            language: 'zh_cn',
                            domain: 'iat',
                            accent: 'mandarin',
                            vad_eos: 5000,
                            dwa: 'wpgs'
                        },
                        data: {
                            status: 0,
                            format: 'audio/L16;rate=16000',
                            encoding: 'raw'
                        }
                    };
                    
                    const frameStr = JSON.stringify(frame);
                    this.addDebugLog(`发送开始帧: ${frameStr}`);
                    this.ws.send(frameStr);
                    resolve();
                };
                
                this.ws.onmessage = (event) => {
                    this.handleWebSocketMessage(event.data);
                };
                
                this.ws.onerror = (error) => {
                    this.addDebugLog(`WebSocket错误: ${error}`);
                    reject(error);
                };
                
                this.ws.onclose = () => {
                    this.addDebugLog('WebSocket连接已关闭');
                    this.isRecording = false;
                    this.sessionValid = false;
                    this.onStatusChange('stopped');
                };
                
            } catch (error) {
                reject(error);
            }
        });
    }
    
    // 处理WebSocket消息
    handleWebSocketMessage(data) {
        try {
            this.addDebugLog(`收到消息: ${data}`);
            
            const result = JSON.parse(data);
            
            if (result.code !== 0) {
                this.addDebugLog(`讯飞API错误: ${result.message} (code: ${result.code})`);
                
                // 如果收到invalid handle，标记会话已失效
                if (result.code === 10165) {
                    this.addDebugLog('⚠ 会话已失效，可能是服务器已关闭连接');
                    this.sessionValid = false;
                }
                
                this.onError(new Error(result.message));
                return;
            }
            
            // 记录sid（会话ID）
            if (result.sid) {
                this.addDebugLog(`会话ID: ${result.sid}`);
                this.sessionId = result.sid;
            }
            
            if (result.data && result.data.result) {
                const wsData = result.data.result.ws || [];
                const text = wsData.map(item => item.cw.map(cw => cw.w).join('')).join('');

                // ===== isFinal 判断 =====
                // 讯飞 IAT 的帧状态字段在 result.data.status（不是 result.data.result.status）
                // status=0: 开始帧, status=1: 中间帧, status=2: 结束帧（最终结果）
                const dataStatus = result.data.status;
                const isFinal = (dataStatus === 2);

                // ===== pgs 文本累积 =====
                // pgs='rpl': 替换当前临时段（preserves confirmedResult，只换当前正在推测的这一段）
                // pgs='apd' 或无 pgs: 追加模式，text 是增量片段，需要拼到当前段末尾
                const pgs = result.data.result.pgs;
                if (pgs === 'rpl') {
                    // rpl：用新推测替换当前临时段，不影响已确认历史
                    this.currentSegment = text;
                } else {
                    // apd：增量追加到当前段
                    this.currentSegment = (this.currentSegment || '') + text;
                }
                this.fullResult = this.confirmedResult + this.currentSegment;

                // 最终帧：将当前段固化进 confirmedResult，重置 currentSegment
                if (isFinal) {
                    this.confirmedResult = this.fullResult;
                    this.currentSegment = '';
                }

                // 检查是否为空识别结果
                if (!text || text.trim() === '') {
                    this.addDebugLog(`⚠ 收到空识别结果 (dataStatus=${dataStatus})`);
                } else {
                    this.addDebugLog(`✓ 识别到文本: "${text}"`);
                }

                this.onResult({
                    text: this.fullResult,
                    isFinal: isFinal,
                    confidence: result.data.result.sn || 0
                });

                this.addDebugLog(`识别结果: "${text}" ${isFinal ? '(最终)' : '(临时)'} pgs=${pgs || 'none'} dataStatus=${dataStatus} 累积="${this.fullResult}"`);

                // 收到最终帧后自动停止录音
                if (isFinal) {
                    this.addDebugLog('✓ 识别完成，自动停止录音');
                    this.recognitionComplete = true;
                    setTimeout(() => {
                        if (this.isRecording) {
                            this.stop();
                        }
                    }, 500);
                }
            } else {
                this.addDebugLog(`收到非识别结果消息: ${JSON.stringify(result)}`);
            }
            
        } catch (error) {
            this.addDebugLog(`解析消息失败: ${error}`);
        }
    }
    
    // 开始录制音频
    startRecording(stream) {
        this.addDebugLog('开始录制音频...');
        
        // 使用AudioContext处理音频
        const audioContext = new (window.AudioContext || window.webkitAudioContext)();
        const actualSampleRate = audioContext.sampleRate;
        
        // 检查AudioContext状态（浏览器可能需要用户交互才能启动）
        if (audioContext.state === 'suspended') {
            this.addDebugLog(`⚠ AudioContext状态: ${audioContext.state}，尝试恢复...`);
            audioContext.resume().then(() => {
                this.addDebugLog(`✓ AudioContext已恢复，状态: ${audioContext.state}`);
            }).catch(err => {
                this.addDebugLog(`❌ AudioContext恢复失败: ${err.message}`);
            });
        }
        this.addDebugLog(`AudioContext状态: ${audioContext.state}, 实际采样率: ${actualSampleRate}Hz（目标16000Hz）`);
        
        const source = audioContext.createMediaStreamSource(stream);
        // ScriptProcessor：buffer=4096，1个输入通道，1个输出通道
        const processor = audioContext.createScriptProcessor(4096, 1, 1);
        
        // ===== 关键修复：重采样缓冲区 =====
        // ScriptProcessor 在 AudioContext 采样率（通常48000Hz）下工作
        // 需要积累足够数据后用 OfflineAudioContext 重采样到 16000Hz 再发送
        const RESAMPLE_CHUNK_FRAMES = 4096 * 3; // 每次重采样约 256ms @ 48kHz
        let resampleBuffer = new Float32Array(0);
        let audioSeq = 0;
        let hasValidAudio = false;
        let maxAmplitude = 0;

        // 将 Float32Array PCM 数据转为 base64 字符串并通过 WS 发送
        const sendPcm16Base64 = (float32Data) => {
            const buffer = new ArrayBuffer(float32Data.length * 2);
            const view = new DataView(buffer);
            for (let i = 0; i < float32Data.length; i++) {
                const sample = Math.max(-1, Math.min(1, float32Data[i]));
                view.setInt16(i * 2, Math.floor(sample * 0x7FFF), true);
            }
            const uint8 = new Uint8Array(buffer);
            let binary = '';
            for (let i = 0; i < uint8.length; i++) binary += String.fromCharCode(uint8[i]);
            const base64Audio = btoa(binary);

            if (this.recognitionComplete || !this.sessionValid) return;
            if (this.ws && this.ws.readyState === WebSocket.OPEN) {
                const frame = { data: { status: 1, format: 'audio/L16;rate=16000', encoding: 'raw', audio: base64Audio } };
                this.ws.send(JSON.stringify(frame));
                audioSeq++;
                if (audioSeq % 10 === 0) {
                    this.addDebugLog(`已发送 ${audioSeq} 个16k重采样音频帧`);
                }
            }
        };

        // 异步重采样并发送
        const flushResampleBuffer = async (data) => {
            try {
                const resampled = await resampleTo16k(data, actualSampleRate);
                sendPcm16Base64(resampled);
            } catch (err) {
                this.addDebugLog(`❌ 重采样失败: ${err.message}`);
            }
        };
        
        processor.onaudioprocess = (e) => {
            if (!this.isRecording) return;
            
            // 获取音频数据（实际采样率）
            const inputData = e.inputBuffer.getChannelData(0);
            
            // 检测音频幅度（判断是否有声音）
            let sum = 0;
            let maxVal = 0;
            let zeroCount = 0;
            for (let i = 0; i < inputData.length; i++) {
                const absVal = Math.abs(inputData[i]);
                sum += absVal;
                maxVal = Math.max(maxVal, absVal);
                if (absVal < 0.0001) zeroCount++;
            }
            const avgAmplitude = sum / inputData.length;
            
            // 前5帧打印详细的音频统计
            if (audioSeq < 5) {
                this.addDebugLog(`音频统计 - 帧${audioSeq+1}: 平均值=${avgAmplitude.toFixed(6)}, 最大值=${maxVal.toFixed(6)}, 零值占比=${(zeroCount/inputData.length*100).toFixed(1)}%, 原始采样率=${actualSampleRate}Hz`);
            }
            
            // 检测是否有有效音频（幅度 > 0.01 认为有声音）
            if (avgAmplitude > 0.01) {
                hasValidAudio = true;
                maxAmplitude = Math.max(maxAmplitude, maxVal);
            }
            
            // 每100帧报告一次音频质量
            if (audioSeq > 0 && audioSeq % 100 === 0) {
                if (hasValidAudio) {
                    this.addDebugLog(`✓ 检测到有效音频，最大幅度: ${(maxAmplitude * 100).toFixed(1)}%`);
                } else {
                    this.addDebugLog(`⚠ 警告：未检测到有效音频信号，请检查麦克风`);
                }
                hasValidAudio = false;
                maxAmplitude = 0;
            }
            
            if (this.recognitionComplete || !this.sessionValid) return;

            // 追加到重采样缓冲区
            const newBuffer = new Float32Array(resampleBuffer.length + inputData.length);
            newBuffer.set(resampleBuffer);
            newBuffer.set(inputData, resampleBuffer.length);
            resampleBuffer = newBuffer;

            // 积累到足够大小后，触发重采样并发送
            if (resampleBuffer.length >= RESAMPLE_CHUNK_FRAMES) {
                const chunk = resampleBuffer.slice(0, RESAMPLE_CHUNK_FRAMES);
                resampleBuffer = resampleBuffer.slice(RESAMPLE_CHUNK_FRAMES);
                flushResampleBuffer(chunk);
            }
        };
        
        source.connect(processor);
        processor.connect(audioContext.destination);
        
        this.audioContext = audioContext;
        this.processor = processor;
        this.mediaStream = stream;
        // 保存引用以便 stop() 时刷剩余缓冲区
        this._resampleBufferRef = () => resampleBuffer;
        this._flushResampleBuffer = flushResampleBuffer;
    }
    
    // 停止录音和识别
    stop() {
        if (!this.isRecording) return;
        
        this.addDebugLog('停止录音...');
        this.isRecording = false;
        
        // 停止音频处理
        if (this.processor) {
            this.processor.disconnect();
            this.processor = null;
        }
        
        // 刷剩余重采样缓冲区（最后几帧语音）
        const remainingData = this._resampleBufferRef ? this._resampleBufferRef() : null;
        if (remainingData && remainingData.length > 0 && this._flushResampleBuffer) {
            this.addDebugLog(`刷剩余缓冲区: ${remainingData.length} 帧`);
            this._flushResampleBuffer(remainingData);
        }
        
        // 延迟发送结束帧（等待最后一个重采样任务完成）
        setTimeout(() => {
            // 发送结束帧
            if (this.ws && this.ws.readyState === WebSocket.OPEN) {
                const frame = {
                    data: {
                        status: 2,  // 2表示音频结束
                        format: 'audio/L16;rate=16000',
                        encoding: 'raw'
                    }
                };
                const frameStr = JSON.stringify(frame);
                this.addDebugLog(`发送结束帧: ${frameStr}`);
                this.ws.send(frameStr);
            }
            
            if (this.audioContext) {
                this.audioContext.close();
                this.audioContext = null;
            }
            
            if (this.mediaStream) {
                this.mediaStream.getTracks().forEach(track => track.stop());
                this.mediaStream = null;
            }
            
            // 延迟关闭WebSocket，确保所有数据发送完成
            setTimeout(() => {
                if (this.ws) {
                    this.ws.close();
                    this.ws = null;
                }
            }, 1000);
        }, 200); // 200ms 留给重采样异步任务完成
        
        // 返回最终识别结果
        return this.fullResult;
    }
    
    // 添加调试日志（会被外部覆盖）
    addDebugLog(message) {
        console.log(`[IflytekAPI] ${message}`);
    }
}

// 导出类
window.IflytekSpeechRecognizer = IflytekSpeechRecognizer;
