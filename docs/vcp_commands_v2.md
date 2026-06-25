| VCP | 功能 | 中文 | 当前值 | 最大 | 类型 | OpenClaw MCP 命令 |
|-----|------|------|--------|------|------|-------------------|
| `0x10` | Brightness | 亮度 | 70 | 100 | rw | `iflyvoice__set_brightness {"value": N}` |
| `0x12` | Contrast | 对比度 | 50 | 100 | rw | `iflyvoice__set_contrast {"value": N}` |
| `0x16` | Video gain: Red | 红色增益 | 50 | 100 | rw | `iflyvoice__set_rgb_gain {"red":N,"green":N,"blue":N}` |
| `0x18` | Video gain: Green | 绿色增益 | 50 | 100 | rw | `iflyvoice__set_rgb_gain {"red":N,"green":N,"blue":N}` |
| `0x1A` | Video gain: Blue | 蓝色增益 | 50 | 100 | rw | `iflyvoice__set_rgb_gain {"red":N,"green":N,"blue":N}` |
| `0x1E` | Auto setup | 自动设置 | 00 | -- | ro | `iflyvoice__vcp_read {"code": "1E"}` |
| `0x20` | Horizontal Position (Phase | 水平位置 | 514 | 65535 | rw | `iflyvoice__vcp_write {"code": "20", "value": N}` |
| `0x30` | Vertical Position (Phase | 垂直位置 | 514 | 65535 | rw | `iflyvoice__vcp_write {"code": "30", "value": N}` |
| `0x60` | Input Source | 输入源选择 | 0f | -- | rw | `iflyvoice__set_input {"code": "0f"}  # 0f=DP-1, 11=HDMI-1` |
| `0x62` | Audio speaker volume | 扬声器音量（0=静音, 100=最大） | 100 | -- | rw | `iflyvoice__display_config {"what": "volume", "value": N}` |
| `0x6C` | Video black level: Red | 视频黑电平(红) | 80 | 100 | rw | `iflyvoice__vcp_write {"code": "6C", "value": N}` |
| `0x6E` | Video black level: Green | 视频黑电平(绿) | 80 | 100 | rw | `iflyvoice__vcp_write {"code": "6E", "value": N}` |
| `0x70` | Video black level: Blue | 视频黑电平(蓝) | 80 | 100 | rw | `iflyvoice__vcp_write {"code": "70", "value": N}` |
| `0x86` | Display Scaling | 缩放模式 | 02 | -- | rw | `iflyvoice__display_config {"what": "scaling", "value": N}  # 1=1:1, 2=full` |
| `0x87` | Sharpness | 锐度 | 5 | 4 | rw | `iflyvoice__vcp_write {"code": "87", "value": N}` |
| `0x8D` | Audio mute/Screen blank | 静音/息屏 | 02 | -- | rw | `iflyvoice__display_config {"what": "mute", "mute": true}` |
| `0xB2` | Flat panel sub-pixel layout | 子像素布局 | 01 | -- | ro | `iflyvoice__vcp_read {"code": "B2"}` |
| `0xB6` | Display technology type | 面板技术类型 | 03 | -- | ro | `iflyvoice__vcp_read {"code": "B6"}` |
| `0xC0` | Display usage time | 累计使用时间 | 14 | -- | ro | `iflyvoice__vcp_read {"code": "C0"}` |
| `0xC8` | Display controller type | 显示控制器ID | 09 | -- | ro | `iflyvoice__vcp_read {"code": "C8"}` |
| `0xCA` | OSD/Button Control | OSD/按键控制 | 01 | -- | rw | `iflyvoice__osd_control {"action": "lock"}  # lock/unlock/read` |
| `0xCC` | OSD Language | OSD语言 | 0d | -- | rw | `iflyvoice__osd_control {"action": "set_lang", "code": 2}  # 2=EN, 0x0d=CN` |
| `0xD6` | Power mode | 电源模式 | 01 | -- | rw | `iflyvoice__vcp_write {"code": "D6", "value": 1}  # 1=on, 4=off` |
| `0xDC` | Display Mode | 显示场景模式 | 00 | -- | rw | `iflyvoice__display_config {"what": "mode", "value": N}` |
| `0xE2` | Manufacturer Specific | 厂商自定义 E2 | 02 | -- | rw | `iflyvoice__vcp_write {"code": "E2", "value": N}` |
| `0xE6` | Manufacturer Specific | 厂商自定义 E6 | 00 | -- | rw | `iflyvoice__vcp_write {"code": "E6", "value": N}` |
| `0xED` | Manufacturer Specific | 厂商自定义 ED | 01 | -- | rw | `iflyvoice__vcp_write {"code": "ED", "value": N}` |
| `0xF8` | Manufacturer Specific | 厂商自定义 F8 | 02 | -- | rw | `iflyvoice__vcp_write {"code": "F8", "value": N}` |

**全量扫描 184 个 VCP 码，28 个可读可用**
