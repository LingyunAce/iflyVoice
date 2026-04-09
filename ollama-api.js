/**
 * ollama-api.js
 * 封装本地 Ollama /api/chat 接口，支持流式输出和多轮对话
 */

const OLLAMA_CONFIG = {
    baseUrl: '',  // 同源代理：请求发到 /ollama/* 由 server.py 转发
    apiPrefix: '/ollama',
    defaultModel: 'qwen3:4b',
    systemPrompt: '你是一个智能语音助手，请用简洁、自然的中文回答用户问题。',
};

class OllamaClient {
    constructor(options = {}) {
        this.baseUrl = options.baseUrl || OLLAMA_CONFIG.baseUrl;
        this.model = options.model || OLLAMA_CONFIG.defaultModel;
        this.systemPrompt = options.systemPrompt || OLLAMA_CONFIG.systemPrompt;

        // 多轮对话历史
        this.history = [];

        // 回调
        this.onToken = options.onToken || (() => {});    // 每个流式 token
        this.onDone = options.onDone || (() => {});      // 完整回答完成
        this.onError = options.onError || (() => {});    // 错误

        // 当前是否正在生成
        this.isGenerating = false;
        this._abortController = null;
    }

    /**
     * 发送消息，流式获取回答
     * @param {string} userText - 用户输入的文本
     */
    async chat(userText) {
        if (this.isGenerating) {
            this.abort();
        }

        this.isGenerating = true;
        this._abortController = new AbortController();

        // 将用户消息加入历史
        this.history.push({ role: 'user', content: userText });

        // 构造消息列表（系统提示 + 历史 + 当前）
        const messages = [
            { role: 'system', content: this.systemPrompt },
            ...this.history,
        ];

        let fullResponse = '';

        try {
            const resp = await fetch(`${this.baseUrl}${OLLAMA_CONFIG.apiPrefix}/api/chat`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                signal: this._abortController.signal,
                body: JSON.stringify({
                    model: this.model,
                    messages,
                    stream: true,
                    options: {
                        temperature: 0.7,
                        top_p: 0.9,
                    },
                }),
            });

            if (!resp.ok) {
                const errText = await resp.text();
                throw new Error(`Ollama HTTP ${resp.status}: ${errText}`);
            }

            const reader = resp.body.getReader();
            const decoder = new TextDecoder('utf-8');

            while (true) {
                const { done, value } = await reader.read();
                if (done) break;

                const chunk = decoder.decode(value, { stream: true });
                // 每行是一个 JSON 对象
                const lines = chunk.split('\n').filter(l => l.trim());
                for (const line of lines) {
                    try {
                        const data = JSON.parse(line);
                        // qwen3 thinking 模式会有 <think>...</think>，过滤掉
                        const token = data.message?.content || '';
                        if (token) {
                            fullResponse += token;
                            this.onToken(token, fullResponse);
                        }
                        if (data.done) {
                            // 过滤掉 <think>...</think> 思考块再存历史
                            const cleanResponse = stripThinkTags(fullResponse);
                            this.history.push({ role: 'assistant', content: cleanResponse });
                            this.isGenerating = false;
                            this.onDone(cleanResponse, fullResponse);
                            return;
                        }
                    } catch (_) { /* 忽略非 JSON 行 */ }
                }
            }

            // 流结束但没收到 done:true（兼容处理）
            const cleanResponse = stripThinkTags(fullResponse);
            this.history.push({ role: 'assistant', content: cleanResponse });
            this.isGenerating = false;
            this.onDone(cleanResponse, fullResponse);

        } catch (err) {
            this.isGenerating = false;
            if (err.name === 'AbortError') return; // 用户主动中断，不报错
            // 回滚最后一条用户消息
            this.history.pop();
            this.onError(err);
        }
    }

    /** 中断当前生成 */
    abort() {
        if (this._abortController) {
            this._abortController.abort();
            this._abortController = null;
        }
        this.isGenerating = false;
    }

    /** 清空对话历史 */
    clearHistory() {
        this.history = [];
    }

    /** 获取可用模型列表 */
    static async fetchModels(baseUrl = OLLAMA_CONFIG.baseUrl) {
        try {
            const resp = await fetch(`${baseUrl}${OLLAMA_CONFIG.apiPrefix}/api/tags`);
            if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
            const data = await resp.json();
            return (data.models || []).map(m => m.name);
        } catch (err) {
            console.error('[Ollama] 获取模型列表失败:', err.message);
            return [];
        }
    }
}

/**
 * 过滤 qwen3 的 <think>...</think> 思考块
 * 可选：保留思考块用于调试，默认过滤
 */
function stripThinkTags(text) {
    return text.replace(/<think>[\s\S]*?<\/think>/g, '').trim();
}

/**
 * 将 Markdown 基本语法转为 HTML（供展示用）
 * 只处理常见格式：加粗、斜体、代码块、行内代码、无序列表、换行
 */
function markdownToHtml(text) {
    let html = text
        // 代码块
        .replace(/```([\w]*)\n?([\s\S]*?)```/g, (_, lang, code) =>
            `<pre class="code-block"><code>${escapeHtml(code.trim())}</code></pre>`)
        // 行内代码
        .replace(/`([^`]+)`/g, (_, c) => `<code class="inline-code">${escapeHtml(c)}</code>`)
        // 加粗
        .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
        // 斜体
        .replace(/\*(.*?)\*/g, '<em>$1</em>')
        // 无序列表
        .replace(/^[-*] (.+)$/gm, '<li>$1</li>')
        .replace(/(<li>.*<\/li>)/s, '<ul>$1</ul>')
        // 换行
        .replace(/\n/g, '<br>');
    return html;
}

function escapeHtml(text) {
    return text
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;');
}

// 挂到全局
window.OllamaClient = OllamaClient;
window.markdownToHtml = markdownToHtml;
window.OLLAMA_CONFIG = OLLAMA_CONFIG;
