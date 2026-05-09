/**
 * sensevoice-api.js — SenseVoiceSmall (xinference) 语音识别客户端
 *
 * 前端录音 → POST /sensevoice/transcribe → server.py → xinference → 返回文字
 *
 * 使用方式:
 *   const sv = new SenseVoiceClient();
 *   sv.transcribe(audioBlob).then(r => console.log(r.text));
 */

class SenseVoiceClient {
    constructor(options = {}) {
        this.apiUrl = options.apiUrl || '/sensevoice/transcribe';
        this.onError = options.onError || (() => {});
    }

    /**
     * 将音频 Blob/ArrayBuffer/File 上传到服务器进行识别
     * @param {Blob|File} audioBlob
     * @returns {Promise<{text: string, success: boolean, error?: string}>}
     */
    async transcribe(audioBlob) {
        try {
            const formData = new FormData();
            formData.append('file', audioBlob, 'recording.webm');

            const resp = await fetch(this.apiUrl, {
                method: 'POST',
                body: formData,
                // 注意：不设置 Content-Type，让浏览器自动加 multipart/form-data; boundary=...
            });

            const data = await resp.json();
            return data;
        } catch (e) {
            console.error('[SenseVoice] 请求异常:', e);
            this.onError(e);
            return { success: false, error: e.message };
        }
    }
}

window.SenseVoiceClient = SenseVoiceClient;
