# 2026-06-25 Daily Report — VCP 码全量审计 + 显示器功能验证

## 今日目标

1. 全面审计 AOC Q27G10ZE 的 VCP 码支持情况（从 184 项 VESA 标准中筛出真正可用的）
2. 逐码测试可用 VCP，区分真伪 rw/ro
3. 修复音量/静音/OSD 控制中的多个 bug
4. 安装外部技能到 OpenClaw

## 完成情况

### 1. VCP 码全量审计

**方法演变**：
- 初版：基于 ddcutil capabilities → 60 个码（含大量误报）
- 终版：全量扫描 184 个 VESA v2.2a 码 → **28 个真正可读**

**发现**：ddcutil capabilities 声明的 60 个码中，31 个实际报错（假 rw），另有 8 个 capabilities 遗漏的码实际可用（如 0x30 垂直位置、0x87 锐度、0xC0 使用时间）。

**生成文档**：
- `docs/vcp_compatibility_report.md` — 按分类分组的支持/不支持对照表
- `docs/vcp_commands.md` / `docs/vcp_commands_v2.md` — 含中文名 + MCP 命令的完整命令表
- `scripts/vcp_table.py` — 自动生成命令表的脚本（全量扫描模式）
- `scripts/scan_all_vcp.py` — VCP 全量扫描工具

### 2. 28 个可读 VCP 码逐码验证

| VCP | 功能 | 读写 | 结论 |
|-----|------|------|------|
| 0x10 | 亮度 | rw ✅ | 核心功能，稳定 |
| 0x12 | 对比度 | rw ✅ | 核心功能，稳定 |
| 0x14 | 色温预设 | rw ✅ | 6500K/7500K/9300K/User1 |
| 0x16/18/1A | RGB 增益 | rw ✅ | 三通道独立可调 |
| 0x1E | 自动设置 | ro ✅ | 只读 |
| 0x20 | 水平位置 | 假 rw | **能读不能写**，514/65535 |
| 0x30 | 垂直位置 | 假 rw | **能读不能写**，514/65535 |
| 0x60 | 输入源 | rw ✅ | DP-1/DP-2/HDMI-1 双向切换 |
| 0x62 | 扬声器音量 | rw ✅ | AOC 反转：100=静音, 0=最大 |
| 0x6C/6E/6F/70 | 黑电平 RGB | rw ✅ | 三通道独立 0-100 |
| 0x86 | 缩放模式 | 假 rw | 能读不能写 |
| 0x87 | 锐度 | 假 rw | **能读（5/4异常），写不了** |
| 0x8D | 静音/息屏 | rw ✅ | **1=静音, 2=取消静音**，记住音量 |
| 0xB2/B6 | 面板信息 | ro ✅ | 子像素RGB条纹、LCD技术 |
| 0xC0 | 使用时间 | ro ✅ | 累计 13 小时 |
| 0xC8 | 控制器ID | ro ✅ | RealTek 编号9 |
| 0xCA | OSD/按键 | rw ✅ | **1=禁用OSD, 2=启用**，物理按键不能锁 |
| 0xCC | OSD语言 | rw ✅ | 全部17种可用，**14(葡语)禁止——关DDC/CI** |
| 0xD6 | 电源模式 | 部分 | **5=关机(单向)，DDC/CI断连需手动开** |
| 0xDC | 场景模式 | rw ✅ | 00-10 全部可切换，DDC/CI稳定 |

### 3. Bug 修复

**音量/静音分离**（核心修复）：
- 问题：0x62 既当音量又当静音，AOC 反转导致混乱
- 修复：静音走 0x8D（1=静音, 2=取消），音量走 0x62
- 0x8D 静音记住当前音量，取消时自动恢复
- 新增 `monitor_mute` + `monitor_volume` 专用 MCP 工具，避免与 `set_volume`（系统音量）混淆

**OSD 控制**：
- 修正 lock/unlock 值（1=禁用, 2=启用）
- 明确 0xCA 不能锁物理按键（AOC 实现限制）
- 0xCC 完整 17 种语言码表
- 0x0e 葡萄牙语标记为禁止（触发 AOC 固件 bug 关闭 DDC/CI）

**DDC/CI 稳定性**：
- `vcp_write` 加自动重试（I2C 瞬时掉线恢复）
- 确认两种断连场景：0xD6=5 关机断电、0xCC=14 固件bug

### 4. WebDDCUtil API 变更

WebDDCUtil API 结构变化：`category_name`/`category_id`/`custom_data` 移除，`owner_id`/`function` 新增。`list_vcp_codes` 已兼容新旧两版。

### 5. 外部技能安装

| 技能 | 来源 | 用途 |
|------|------|------|
| `westockdata` | workbuddy | A股/港股/美股行情 |
| `aihot` | workbuddy | AI 中文资讯 |
| `tencent-news` | workbuddy skill | 7×24 新闻搜索 |
| `neodata-financial-search` | workbuddy skill_2053083392235933696 | 金融数据搜索 |

## 今日提交（15 个 commit）

```
9b1d9a8 fix(ddcci): add retry on vcp_write
7657eaa docs(mcp): full OSD language code table + ban Portuguese (14)
85f836a fix(osd): correct AOC OSD lock/unlock values
fd9f26f fix(mute): separate mute (0x8D) from volume (0x62)
92d0d06 fix(volume): remove reversal, pass AOC values directly
51ad055 fix(mcp): add dedicated monitor_mute + monitor_volume tools
4fc0c05 fix(volume): auto-reverse AOC volume transparently
a06f663 docs(mcp): note AOC reversed volume
0782aa4 docs(vcp): AOC 0x62 volume is reversed
0a861d5 fix(vcp): add 0x62 speaker volume to command table (v2)
8f57ac5 fix(vcp): full scan 184 codes — found 27 truly readable
4e1cf79 docs(vcp): add Chinese translations to VCP command table
9bb4f1b docs(vcp): add 29-code command reference with MCP tool calls
10a61e4 feat(vcp): wrap all 29 working VCP codes as API + MCP tools
b4a1057 docs(vcp): add sorted VCP compatibility report
```

## 待办

1. **推送分支**：`git push origin rk3576_lubancat`（100+ commits）
2. **外接麦克风**：板子自带 mic 灵敏度低
3. **CosyVoice2 TTS 部署**：xinference 上缺少 TTS 模型
4. **AOC 固件限制**：0x20/30/86/87 假 rw，0xCA 不能锁按键，0xD6 单向——硬件/固件层面的限制，代码无法解决
