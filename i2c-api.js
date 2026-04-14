/**
 * i2c-api.js — DDC/CI 显示器 I2C 控制模块
 * 
 * 通过 ADB shell + i2cset 命令控制显示器参数（亮度、对比度、输入源等）
 * 
 * DDC/CI 协议格式：
 *   i2cset -y -f <bus> <slave_addr> <MAGIC1> <MAGIC2> <opcode> <vcp_code> <val_hi> <val_lo> <checksum> i
 * 
 * Checksum 算法：XOR 累加
 *   初始值 = (slave_addr << 1)
 *   依次 ^= MAGIC1 ^ MAGIC2 ^ opcode ^ vcp_code ^ val_hi ^ val_lo
 */

const I2C_CONFIG = {
    // ADB 设备配置
    adbPath: 'adb',                    // adb 可执行文件路径（需要 PATH 中能找到）
    apiPrefix: '/i2c',                 // 后端代理路由前缀

    // I2C 总线 & 从机地址
    bus: 1,                            // I2C 总线编号
    slaveAddr: 0x37,                   // DDC/CI 从机地址

    // DDC/CI 固定头
    MAGIC1: 0x51,

    // VCP Code 映射表
    VCP_CODES: {
        brightness:  0x10,             // 亮度 (0-100)
        contrast:    0x12,             // 对比度 (0-100)
        redGain:     0x13,             // 红色增益 (0-100)
        greenGain:   0x14,             // 绿色增益 (0-100)
        blueGain:    0x15,             // 蓝色增益 (0-100)
        inputSource: 0x60,             // 输入源切换
        powerMode:   0xD6,             // 电源控制
        sceneMode:   0x52,             // 场景模式
    },

    // 输入源值映射
    INPUT_SOURCE: {
        DP:    0x11,
        HDMI:  0x12,
        VGA:   0x15,
        TYPEC: 0x1F,
    },

    // 电源控制值
    POWER_MODE: {
        ON:  0x01,
        OFF: 0x06,
    },
};


/**
 * 计算 DDC/CI XOR 校验和
 * @param {number} slaveAddr - 从机地址 (如 0x37)
 * @param {number[]} dataBytes - 数据字节序列 [MAGIC1, MAGIC2, opcode, vcpCode, valHi, valLo]
 * @returns {number} checksum 字节 (0x00-0xFF)
 */
function calcChecksum(slaveAddr, dataBytes) {
    let xor = (slaveAddr << 1) & 0xFF;
    for (const b of dataBytes) {
        xor ^= b;
    }
    return xor;
}


/**
 * 构建 DDC/CI 写命令的完整字节数组
 * @param {number} vcpCode - VCP 控制码 (如 0x10=亮度)
 * @param {number} value - 控制值 (如 50 表示亮度50%)
 * @returns {{bytes: number[], cmdStr: string}} 字节数组和可读的 i2cset 命令字符串
 */
function buildDdcCiCommand(vcpCode, value) {
    const val = Math.max(0, Math.min(100, Math.round(value))); // 限制 0-100
    const valHi = (val >> 8) & 0xFF;  // 高字节（0-100 范围内总是 0）
    const valLo = val & 0xFF;          // 低字节

    const dataLen = 4;  // opcode(1) + vcpCode(1) + valHi(1) + valLo(1)
    const magic2 = 0x80 | dataLen;

    const dataBytes = [
        I2C_CONFIG.MAGIC1,      // 0x51
        magic2,                  // 0x80 | length = 0x84
        0x03,                    // Write opcode
        vcpCode,                 // VCP code
        valHi,                   // value high byte
        valLo,                   // value low byte
    ];

    const checksum = calcChecksum(I2C_CONFIG.slaveAddr, dataBytes);

    const bytes = [I2C_CONFIG.slaveAddr, ...dataBytes, checksum];

    // 构建可显示的命令字符串（每个字节统一 2 位 hex + 0x 前缀）
    const toHex = (b) => ('0' + b.toString(16).toUpperCase()).slice(-2);
    const hexParts = bytes.map(b => '0x' + toHex(b));
    const cmdStr = `i2cset -y -f ${I2C_CONFIG.bus} ${hexParts.join(' ')} i`;

    return { bytes, cmdStr, toHex };
}


class I2cController {
    constructor() {
        this.connected = false;       // ADB 是否已连接
        this.lastCommand = null;      // 最近一次执行的命令
        this.onStatusChange = null;   // 状态变化回调
    }

    /**
     * 检测 ADB 连接状态
     */
    async checkConnection() {
        try {
            const resp = await fetch(`${I2C_CONFIG.apiPrefix}/adb/status`, {
                method: 'GET',
                headers: { 'Content-Type': 'application/json' },
            });
            const data = await resp.json();
            this.connected = data.connected === true;
            if (this.onStatusChange) {
                this.onStatusChange(this.connected ? 'connected' : 'disconnected', data);
            }
            return data;
        } catch (e) {
            this.connected = false;
            if (this.onStatusChange) {
                this.onStatusChange('error', { error: e.message });
            }
            throw e;
        }
    }

    /**
     * 发送 DDC/CI 写命令到显示器
     * @param {string} controlName - 控制名称 ('brightness', 'contrast' 等)
     * @param {number} value - 目标值 (通常 0-100)
     * @returns {Promise<object>} 执行结果
     */
    async setControl(controlName, value) {
        const vcpCode = I2C_CONFIG.VCP_CODES[controlName];
        if (vcpCode === undefined) {
            throw new Error(`未知的控制项: ${controlName}`);
        }

        const { bytes, cmdStr, toHex } = buildDdcCiCommand(vcpCode, value);

        this.lastCommand = { controlName, value, vcpCode, bytes, cmdStr };

        try {
            const resp = await fetch(`${I2C_CONFIG.apiPrefix}/i2cset`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    command: 'i2cset',
                    args: ['-y', '-f', String(I2C_CONFIG.bus),
                        ...bytes.map(b => '0x' + toHex(b)),
                        'i'],
                }),
            });

            const result = await resp.json();
            if (!result.success) {
                throw new Error(result.error || 'i2cset 执行失败');
            }
            return result;
        } catch (e) {
            console.error('[I2C] 控制失败:', e);
            throw e;
        }
    }

    /**
     * 快捷方法：设置亮度
     * @param {number} brightness - 亮度值 0-100
     */
    async setBrightness(brightness) {
        return this.setControl('brightness', brightness);
    }

    /**
     * 快捷方法：设置对比度
     * @param {number} contrast - 对比度值 0-100
     */
    async setContrast(contrast) {
        return this.setControl('contrast', contrast);
    }

    /**
     * 解析语音指令中的控制意图
     * 支持的指令格式示例:
     *   "把亮度调到50" / "亮度调高一点" / "屏幕亮一点" / "对比度设为70"
     *   "把屏幕关掉" / "打开显示器"
     * @param {string} text - 识别出的文本
     * @returns {{action: string, control: string, value: number|null}|null}
     */
    parseVoiceCommand(text) {
        if (!text) return null;

        const t = text.toLowerCase();

        // ── 亮度相关 ──
        // 支持: "亮度调到50" "亮度调成10%" "把亮度调成20" "亮度设为30" "亮度:40" "亮度 50"
        let brightnessMatch =
            t.match(/亮度\s*(?:调|设)(?:成|为|到|整?到)?\s*(\d{1,3})%?/) ||
            t.match(/(?:把\s*)?亮度\s*(?:调|设)(?:成|为|到|整?到)?\s*(\d{1,3})%?/) ||
            t.match(/(?:亮度|屏幕)\s*[:：]?\s*(\d{1,3})%?/);

        if (brightnessMatch) {
            return {
                action: 'set',
                control: 'brightness',
                value: parseInt(brightnessMatch[1], 10),
            };
        }

        // 亮度极值指令：最高/最亮 → 100%，最低/最暗 → 0%
        // 注意：必须含"最"字，排除"调高/调低"等模糊指令
        if (/(?:亮度|屏幕)\s*(?:调|设)?(?:成|为|到)?\s*(?:最高|最大|最亮|full)/.test(t)) {
            return { action: 'set', control: 'brightness', value: 100 };
        }
        if (/(?:亮度|屏幕)\s*(?:调|设)?(?:成|为|到)?\s*(?:最低|最小|最暗)/.test(t)) {
            return { action: 'set', control: 'brightness', value: 0 };
        }

        // 亮度模糊指令
        if (/亮度.*调高|(屏幕|显示器).*亮一点|更亮|增加亮度/.test(t)) {
            return { action: 'adjust', control: 'brightness', delta: +10 };
        }
        if (/亮度.*调低|(屏幕|显示器).*暗一点|更暗|降低亮度/.test(t)) {
            return { action: 'adjust', control: 'brightness', delta: -10 };
        }

        // ── 对比度相关 ──
        let contrastMatch =
            t.match(/对比度\s*(?:调|设)(?:成|为|到|整?到)?\s*(\d{1,3})%?/) ||
            t.match(/(?:把\s*)?对比度\s*(?:调|设)(?:成|为|到|整?到)?\s*(\d{1,3})%?/);

        if (contrastMatch) {
            return {
                action: 'set',
                control: 'contrast',
                value: parseInt(contrastMatch[1], 10),
            };
        }

        // 对比度极值指令（必须含"最"字）
        if (/(?:对比度)\s*(?:调|设)?(?:成|为|到)?\s*(?:最高|最大)/.test(t)) {
            return { action: 'set', control: 'contrast', value: 100 };
        }
        if (/(?:对比度)\s*(?:调|设)?(?:成|为|到)?\s*(?:最低|最小)/.test(t)) {
            return { action: 'set', control: 'contrast', value: 0 };
        }

        if (/对比度.*调高|增加对比度/.test(t)) {
            return { action: 'adjust', control: 'contrast', delta: +10 };
        }
        if (/对比度.*调低|降低对比度/.test(t)) {
            return { action: 'adjust', control: 'contrast', delta: -10 };
        }

        // ── 电源控制 ──

        if (/打开?(?:显示器|屏幕)|开启?(?:显示器|屏幕)|唤醒/.test(t)) {
            return { action: 'set', control: 'powerMode', value: 0x01 };  // ON
        }

        return null;
    }
}


// 挂到全局
window.I2cController = I2cController;
window.I2C_CONFIG = I2C_CONFIG;
window.buildDdcCiCommand = buildDdcCiCommand;
window.calcChecksum = calcChecksum;
