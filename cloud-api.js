/**
 * cloud-api.js — 火山引擎（豆包）云端模型客户端
 * 
 * 使用 OpenAI 兼容格式，通过 /cloud/* 代理访问火山引擎 API
 * 支持流式输出（SSE）和多轮对话
 */

const CLOUD_CONFIG = {
    apiPrefix: '/cloud',           // server.py 代理路由前缀
    defaultModel: 'doubao-1-5-pro-32k-250115',  // coding-plan 默认模型
    systemPrompt: '你是一个智能语音助手，具备显示器控制能力。当用户要求调整亮度、对比度等显示器参数时，系统会自动通过I2C指令执行，你需要友好地确认操作结果。',
};


class CloudClient {
    constructor(options = {}) {
        this.model = options.model || CLOUD_CONFIG.defaultModel;
        this.systemPrompt = options.systemPrompt || CLOUD_CONFIG.systemPrompt;

        // 多轮对话历史
        this.history = [];

        // 回调
        this.onToken = options.onToken || (() => {});
        this.onDone = options.onDone || (() => {});
        this.onError = options.onError || (() => {});

        // 状态
        this.isGenerating = false;
        this._abortController = null;
    }

    /**
     * 发送消息，流式获取回答（OpenAI 兼容 SSE 格式）
     * @param {string} userText - 用户输入的文本
     */
    async chat(userText) {
        if (this.isGenerating) {
            this.abort();
        }

        this.isGenerating = true;
        this._abortController = new AbortController();

        // 加入历史
        this.history.push({ role: 'user', content: userText });

        const messages = [
            { role: 'system', content: this.systemPrompt },
            ...this.history,
        ];

        let fullResponse = '';

        try {
            const resp = await fetch(`${CLOUD_CONFIG.apiPrefix}/chat/completions`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                signal: this._abortController.signal,
                body: JSON.stringify({
                    model: this.model,
                    messages,
                    stream: true,
                    temperature: 0.7,
                    top_p: 0.9,
                    max_tokens: 4096,
                }),
            });

            if (!resp.ok) {
                const errData = await resp.json().catch(() => ({}));
                throw new Error(errData.error?.message || `Cloud API HTTP ${resp.status}`);
            }

            const reader = resp.body.getReader();
            const decoder = new TextDecoder('utf-8');
            let buffer = '';

            while (true) {
                const { done, value } = await reader.read();
                if (done) break;

                buffer += decoder.decode(value, { stream: true });
                const lines = buffer.split('\n');
                buffer = lines.pop() || '';  // 保留不完整的行

                for (const line of lines) {
                    const trimmed = line.trim();
                    if (!trimmed || trimmed === 'data: [DONE]') continue;

                    if (trimmed.startsWith('data: ')) {
                        try {
                            const data = JSON.parse(trimmed.slice(6));
                            const delta = data.choices?.[0]?.delta?.content || '';
                            if (delta) {
                                fullResponse += delta;
                                this.onToken(delta, fullResponse);
                            }

                            if (data.choices?.[0]?.finish_reason) {
                                this.history.push({ role: 'assistant', content: fullResponse });
                                this.isGenerating = false;
                                this.onDone(fullResponse, fullResponse);
                                return;
                            }
                        } catch (_) { /* 忽略解析错误 */ }
                    }
                }
            }

            // 流正常结束
            if (fullResponse) {
                this.history.push({ role: 'assistant', content: fullResponse });
            }
            this.isGenerating = false;
            this.onDone(fullResponse, fullResponse);

        } catch (err) {
            this.isGenerating = false;
            if (err.name === 'AbortError') return;
            this.history.pop();  // 回滚用户消息
            this.onError(err);
        }
    }

    abort() {
        if (this._abortController) {
            this._abortController.abort();
            this._abortController = null;
        }
        this.isGenerating = false;
    }

    clearHistory() {
        this.history = [];
    }

    /**
     * 获取可用模型列表（静态配置）
     */
    static getModels() {
        return [
            { id: 'doubao-1-5-pro-32k-250115', name: 'Doubao-1.5-Pro-32K (coding-plan)' },
            { id: 'doubao-1-5-lite-32k-250115', name: 'Doubao-1.5-Lite-32K' },
            { id: 'doubao-pro-32k', name: 'Doubao-Pro-32K' },
            { id: 'doubao-lite-32k', name: 'Doubao-Lite-32K' },
        ];
    }
}


// 挂到全局
window.CloudClient = CloudClient;
window.CLOUD_CONFIG = CLOUD_CONFIG;
