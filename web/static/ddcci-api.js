/**
 * ddcci-api.js — 外置屏幕 DDC/CI 控制模块
 *
 * 通过 server.py 的 /ddcci/* 路由调用 Windows dxva2.dll
 * - 亮度：VCP 0x10 (0-100)
 * - 对比度：VCP 0x12 (0-100)
 * - 状态检测：GetVCPFeatureAndVCPReply(VCP 0x00 Manufacturer ID)
 *
 * 适用设备：CMCC-YH201（中国移动 Android 显示屏，HDMI 外接）
 */

const DDCCI_CONFIG = {
    apiPrefix: '/ddcci',   // server.py 代理路由前缀
};


/**
 * 安全解析 JSON 响应
 * 防止服务器返回 HTML（404/500 页面）导致 JSON.parse 炸掉
 */
async function _safeJsonResp(resp, actionName) {
    const ct = (resp.headers.get('Content-Type') || '').toLowerCase();
    // 如果不是 JSON 格式，说明 server 路由不存在或出错了
    if (!ct.includes('application/json')) {
        let text = '';
        try { text = await resp.text(); } catch (_) {}
        const preview = text.slice(0, 120).replace(/\n/g, ' ');
        throw new Error(`Server returned non-JSON (${resp.status} ${ct}): ${preview}`);
    }
    return await resp.json();
}


class DdcciClient {
    constructor() {
        this.connected = false;
        this.supported = false;
    }

    /**
     * 检测 DDC/CI 物理显示器是否可用
     */
    async checkStatus() {
        try {
            const resp = await fetch(`${DDCCI_CONFIG.apiPrefix}/status`);
            if (!resp.ok) {
                throw new Error(`HTTP ${resp.status}`);
            }
            const data = await _safeJsonResp(resp, 'status');
            this.connected = data.connected === true;
            this.supported = data.supported === true;
            return data;
        } catch (e) {
            this.connected = false;
            this.supported = false;
            return { connected: false, supported: false, error: e.message };
        }
    }

    /**
     * 设置亮度 VCP 0x10 (0-100)
     */
    async setBrightness(value) {
        const val = Math.max(0, Math.min(100, Math.round(value)));
        const resp = await fetch(`${DDCCI_CONFIG.apiPrefix}/brightness`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ value: val }),
        });
        if (!resp.ok) {
            throw new Error(`HTTP ${resp.status}`);
        }
        return await _safeJsonResp(resp, 'brightness');
    }

    /**
     * 读取当前对比度 VCP 0x12
     */
    async getContrast() {
        const resp = await fetch(`${DDCCI_CONFIG.apiPrefix}/contrast_read`);
        if (!resp.ok) {
            throw new Error(`HTTP ${resp.status}`);
        }
        return await _safeJsonResp(resp, 'contrast');
    }

    /**
     * 设置对比度 VCP 0x12 (0-100)
     */
    async setContrast(value) {
        const val = Math.max(0, Math.min(100, Math.round(value)));
        const resp = await fetch(`${DDCCI_CONFIG.apiPrefix}/contrast`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ value: val }),
        });
        if (!resp.ok) {
            throw new Error(`HTTP ${resp.status}`);
        }
        return await _safeJsonResp(resp, 'contrast');
    }
}


window.DdcciClient = DdcciClient;
window.DDCCI_CONFIG = DDCCI_CONFIG;
