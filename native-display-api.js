/**
 * native-display-api.js — Windows 内置显示器亮度/对比度控制
 *
 * 通过 server.py 的 /native/* 路由调用 PowerShell WMI 接口
 * - 亮度：通过 WmiMonitorBrightnessMethods.WmiSetBrightness
 * - 对比度：通过 WmiMonitorContrastMethods.WmiSetContrast（如可用）
 */

const NATIVE_CONFIG = {
    apiPrefix: '/native',   // server.py 代理路由前缀
};


class NativeDisplayClient {
    constructor() {
        this.connected = false;
        this.instanceName = null;
        this._cachedBrightness = null;
    }

    /**
     * 检测内置显示器是否可用（WMI 接口）
     */
    async checkConnection() {
        try {
            const resp = await fetch(`${NATIVE_CONFIG.apiPrefix}/status`);
            const data = await resp.json();
            this.connected = data.connected === true;
            this.instanceName = data.instanceName || null;
            this._cachedBrightness = data.brightness != null ? data.brightness : null;
            return data;
        } catch (e) {
            this.connected = false;
            return { connected: false, error: e.message };
        }
    }

    /**
     * 设置亮度（0-100）
     */
    async setBrightness(value) {
        const val = Math.max(0, Math.min(100, Math.round(value)));
        const resp = await fetch(`${NATIVE_CONFIG.apiPrefix}/brightness`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ value: val }),
        });
        const data = await resp.json();
        if (data.success) {
            this._cachedBrightness = val;
        }
        return data;
    }

    /**
     * 设置对比度（0-100）
     * 注意：大多数 Windows 笔记本不支持通过 WMI 控制对比度
     */
    async setContrast(value) {
        const val = Math.max(0, Math.min(100, Math.round(value)));
        const resp = await fetch(`${NATIVE_CONFIG.apiPrefix}/contrast`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ value: val }),
        });
        return await resp.json();
    }

    /**
     * 读取当前亮度（回读确认用）
     * @returns {Promise<number|null>} 0-100 或 null
     */
    async getBrightness() {
        try {
            const resp = await fetch(`${NATIVE_CONFIG.apiPrefix}/brightness`);
            const data = await resp.json();
            const val = data.brightness ?? data.currentBrightness ?? data.value;
            this._cachedBrightness = val;
            return val;
        } catch {
            return this._cachedBrightness;
        }
    }

    /**
     * 设置色温（0-100）：0=最暖(2700K)，100=最冷(6500K)
     * 通过 SetDeviceGammaRamp 实现软件级色温调整
     */
    async setColorTemp(value) {
        const val = Math.max(0, Math.min(100, Math.round(value)));
        const resp = await fetch(`${NATIVE_CONFIG.apiPrefix}/color_temp`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ value: val }),
        });
        return await resp.json();
    }

    /**
     * 设置伽马值（0-100）：0=gamma 2.5(暗)，50=gamma 1.0(标准)，100=gamma 0.5(亮)
     */
    async setGamma(value) {
        const val = Math.max(0, Math.min(100, Math.round(value)));
        const resp = await fetch(`${NATIVE_CONFIG.apiPrefix}/gamma`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ value: val }),
        });
        return await resp.json();
    }

    /**
     * 读取当前 gamma 和色温（从 GPU 曲线估算）
     * @returns {Promise<{gamma: number, colorTemp: number, gammaVal: number, error?: string}>}
     */
    async getGamma() {
        const resp = await fetch(`${NATIVE_CONFIG.apiPrefix}/gamma`);
        return await resp.json();
    }
}


window.NativeDisplayClient = NativeDisplayClient;
window.NATIVE_CONFIG = NATIVE_CONFIG;
