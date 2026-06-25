| VCP | 功能 | 当前值 | 最大 | 类型 | OpenClaw MCP 命令 |
|-----|------|--------|------|------|-------------------|
| `0x02` | New control value | -- | -- | ro | `iflyvoice__vcp_read {"code": "02"}` |
| `0x0C` | Color temperature request | -- | -- | ro | `iflyvoice__vcp_read {"code": "0C"}` |
| `0x10` | Brightness | 100 | 100 | rw | `iflyvoice__set_brightness {"value": N}` |
| `0x12` | Contrast | 60 | 100 | rw | `iflyvoice__set_contrast {"value": N}` |
| `0x14` | Select color preset | -- | -- | rw | `iflyvoice__set_color_temp {"preset": "6500 K"}` |
| `0x16` | Video gain: Red | 50 | 100 | rw | `iflyvoice__set_rgb_gain {"red":50,"green":50,"blue":50}` |
| `0x18` | Video gain: Green | 50 | 100 | rw | `iflyvoice__set_rgb_gain {"red":50,"green":50,"blue":50}` |
| `0x1A` | Video gain: Blue | 50 | 100 | rw | `iflyvoice__set_rgb_gain {"red":50,"green":50,"blue":50}` |
| `0x20` | Horizontal Position (Phase | 514 | 65535 | rw | `iflyvoice__vcp_write {"code": "20", "value": N}` |
| `0x52` | Active control | -- | -- | ro | `iflyvoice__vcp_read {"code": "52"}` |
| `0x60` | Input Source | 0f | -- | rw | `iflyvoice__set_input {"code": "0f"}  # 0f=DP-1, 11=HDMI-1` |
| `0x62` | Audio speaker volume | -- | -- | rw | `iflyvoice__display_config {"what": "volume", "value": N}` |
| `0x6C` | Video black level: Red | 80 | 100 | rw | `iflyvoice__vcp_write {"code": "6C", "value": N}` |
| `0x86` | Display Scaling | 02 | -- | rw | `iflyvoice__display_config {"what": "scaling", "value": N}  # 1=1:1, 2=full` |
| `0x8D` | Audio mute/Screen blank | 02 | -- | rw | `iflyvoice__display_config {"what": "mute", "mute": true}` |
| `0xAC` | Horizontal frequency | -- | -- | ro | `iflyvoice__vcp_read {"code": "AC"}` |
| `0xAE` | Vertical frequency | -- | -- | ro | `iflyvoice__vcp_read {"code": "AE"}` |
| `0xB2` | Flat panel sub-pixel layout | 01 | -- | ro | `iflyvoice__vcp_read {"code": "B2"}` |
| `0xB6` | Display technology type | 03 | -- | ro | `iflyvoice__vcp_read {"code": "B6"}` |
| `0xC6` | Application enable key | -- | -- | ro | `iflyvoice__vcp_read {"code": "C6"}` |
| `0xC8` | Display controller type | 09 | -- | ro | `iflyvoice__vcp_read {"code": "C8"}` |
| `0xC9` | Display firmware level | -- | -- | ro | `iflyvoice__vcp_read {"code": "C9"}` |
| `0xCA` | OSD/Button Control | 01 | -- | rw | `iflyvoice__osd_control {"action": "lock"}  # lock/unlock/read` |
| `0xCC` | OSD Language | 0d | -- | rw | `iflyvoice__osd_control {"action": "set_lang", "code": 2}  # 2=EN, 0x0d=CN` |
| `0xD6` | Power mode | 01 | -- | rw | `iflyvoice__vcp_write {"code": "D6", "value": 1}  # 1=on, 4=off` |
| `0xDC` | Display Mode | 00 | -- | rw | `iflyvoice__display_config {"what": "mode", "value": N}` |
| `0xDF` | VCP Version | -- | -- | ro | `iflyvoice__vcp_read {"code": "DF"}` |
| `0xE2` | Manufacturer Specific | 02 | -- | rw | `iflyvoice__vcp_write {"code": "E2", "value": N}` |
| `0xF8` | Manufacturer Specific | 02 | -- | rw | `iflyvoice__vcp_write {"code": "F8", "value": N}` |

**共 29 个可用 VCP 码**
