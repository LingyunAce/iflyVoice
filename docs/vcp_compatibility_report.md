[DEBUG] ddcutil: rc=0, len=7338
[DEBUG] Found 60 supported VCP codes
# VCP Compatibility Report
## Monitor: AOC Q27G10ZE (MCCS 2.2) vs VESA v2.2a (184 codes)
**Supported: 51 | Not Supported: 133 | Total: 184**

## ✅ Supported VCP Codes (51)
| VCP | Name | Type | Category | Description |
|-----|------|------|----------|-------------|
### DDC/CI Capabilities
| 0x60 | Input Select | rw | DDC/CI Capabilities | Select video input source (analog, DVI, HDMI, DisplayPort, etc.). |
| 0x62 | Audio: Speaker Volume | rw | DDC/CI Capabilities | Adjust volume (01h‑FEh, FFh = mute). |
| 0xAC | Horizontal Frequency | ro | DDC/CI Capabilities | Current horizontal sync frequency (Hz). 00h = not synced, FFh = out of range. |
| 0xAE | Vertical Frequency | ro | DDC/CI Capabilities | Current vertical sync frequency (0.01Hz). 00h = not synced, FFh = out of range. |
| 0xB2 | Flat Panel Sub‑Pixel Layout | ro | DDC/CI Capabilities | Return LCD sub‑pixel structure (RGB stripe, delta, etc.). |
| 0xB6 | Display Technology Type | ro | DDC/CI Capabilities | Return base technology (CRT, LCD, plasma, OLED, etc.). |
| 0xC6 | Application Enable Key | rw | DDC/CI Capabilities | Enable/disable application reports (OSD/button events). |
| 0xC8 | Display Controller ID | ro | DDC/CI Capabilities | Manufacturer ID and unique chip ID. |
| 0xC9 | Display Firmware Level | ro | DDC/CI Capabilities | Firmware version and revision (e.g., 3.5). |

### Display Controls
| 0x86 | Display Scaling | rw | Display Controls | Select scaling mode (no scaling, max, zoom, etc.). |
| 0x8D | Audio Mute / Screen Blank | rw | Display Controls | Mute audio and/or blank screen. |
| 0xA0 | 6 Axis Hue Control: Magenta | rw | Display Controls | Adjust magenta hue. |
| 0xCA | OSD/Button Control | rw | Display Controls | Enable/disable OSD and button events, report button presses. |
| 0xCC | OSD Language | rw | Display Controls | Select OSD language (capability string lists supported languages). |
| 0xD6 | Power Mode | rw | Display Controls | Set power mode (DPM/DPMS states: On, Standby, Suspend, Off, Power Off). |
| 0xDC | Display Application | rw | Display Controls | Select application preset (office, movie, games, etc.). |
| 0xDF | VCP Version | ro | Display Controls | MCCS version and revision (e.g., 2.2). Mandatory. |

### Image Adjustment
| 0x0C | User Color Temperature | rw | Image Adjustment | Set color temperature in Kelvin (base 3000K + increment * multiplier). |
| 0x10 | Luminance | rw | Image Adjustment | Display luminance (brightness). |
| 0x11 | Flesh Tone Enhancement | rw | Image Adjustment | Select contrast enhancement algorithm (bitmask). |
| 0x12 | Contrast | rw | Image Adjustment | Increasing (decreasing) this value will increase (decrease) the Contrast of the  |
| 0x13 | Backlight Control (deprecated) | rw | Image Adjustment | Deprecated – use separate backlight controls (6Bh, 6Dh, 6Fh, 71h). |
| 0x14 | Select Color Preset | rw | Image Adjustment | Select color temperature preset (sRGB, native, 6500K, etc.). |
| 0x16 | Video Gain (Drive): Red | rw | Image Adjustment | Adjust red gain (luminance of red pixels). |
| 0x18 | Video Gain (Drive): Green | rw | Image Adjustment | Adjust green gain. |
| 0x1A | Video Gain (Drive): Blue | rw | Image Adjustment | Adjust blue gain. |
| 0x20 | Horizontal Position (Phase) | rw | Image Adjustment | Move image left/right. |
| 0x52 | Active Control | ro | Image Adjustment | FIFO of changed VCP codes (used with 02h). |
| 0x56 | Horizontal Moiré | rw | Image Adjustment | Cancel horizontal moiré. |
| 0x58 | Vertical Moiré | rw | Image Adjustment | Cancel vertical moiré. |
| 0x59 | 6 Axis Saturation Control: Red | rw | Image Adjustment | Adjust red saturation (7Fh = nominal). |
| 0x5B | 6 Axis Saturation Control: Green | rw | Image Adjustment | Adjust green saturation. |
| 0x6B | Backlight Level: White | rw | Image Adjustment | Adjust white backlight level. |
| 0x6C | Video Black Level: Red | rw | Image Adjustment | Adjust red black level. |
| 0x71 | Backlight Level: Blue | rw | Image Adjustment | Adjust blue backlight level. |
| 0x72 | Gamma | rw | Image Adjustment | Select absolute or relative gamma value (with tolerance). |
| 0x73 | LUT Size | ro | Image Adjustment | Return size (entries and bits/entry) of Red/Green/Blue LUTs. |
| 0x74 | Single Point LUT Operation | rw | Image Adjustment | Read/write a single LUT entry. |
| 0x75 | Block LUT Operation | rw | Image Adjustment | Read/write a block of LUT entries. |
| 0x76 | Remote Procedure Call | wo | Image Adjustment | Execute a resident routine/macro (e.g., spline LUT loading). |
| 0x78 | Display Identification Data Operation | ro | Image Adjustment | Read EDID or DisplayID block (128 bytes). |
| 0x7C | Adjust Zoom | rw | Image Adjustment | Adjust projection lens zoom. |

### Manufacturer Specific
| 0xE1 | Manufacturer Specific E1 | rw | Manufacturer Specific | OEM‑defined control. |
| 0xE2 | Manufacturer Specific E2 | rw | Manufacturer Specific | OEM‑defined control. |
| 0xF8 | Manufacturer Specific F8 | rw | Manufacturer Specific | OEM‑defined control. |
| 0xFD | Manufacturer Specific FD | rw | Manufacturer Specific | OEM‑defined control. |
| 0xFF | Manufacturer Specific FF | rw | Manufacturer Specific | OEM‑defined control. |

### Preset Operations
| 0x02 | New Control Value | rw | Preset Operations | Indicate that one or more VCP values have changed (for synchronization). |
| 0x04 | Restore Factory Defaults | wo | Preset Operations | Restore all factory presets (luminance, contrast, geometry, color, TV). |
| 0x05 | Restore Factory Luminance/Contrast Defaults | wo | Preset Operations | Restore factory defaults for luminance and contrast. |
| 0x08 | Restore Factory Color Defaults | wo | Preset Operations | Restore factory defaults for color settings. |

## ❌ Not Supported VCP Codes (133)
| VCP | Name | Type | Category | Description |
|-----|------|------|----------|-------------|
### DDC/CI Capabilities
| 0x63 | Audio: Speaker Select | rw | DDC/CI Capabilities | Select speaker pair (FL/FR, SL/SR, etc.). |
| 0x64 | Audio: Microphone Volume | rw | DDC/CI Capabilities | Adjust microphone gain. |
| 0x65 | Audio: Jack Connection Status | ro | DDC/CI Capabilities | Read available and connected audio channels (bitmask). |
| 0xB4 | Source Timing Mode | rw | DDC/CI Capabilities | Declare upcoming video timing (DMT, CEA DTV, or CVT descriptor). |
| 0xB5 | Source Color Coding | wo | DDC/CI Capabilities | Specify color coding (RGB 4:4:4, YCbCr 4:4:4, 4:2:2). |
| 0xB7 | Monitor Status | ro | DDC/CI Capabilities | DPVL monitor status (error, readiness, scan mode). |
| 0xB8 | Packet Count | rw | DDC/CI Capabilities | DPVL packet counter (rollover at FFFFh). |
| 0xB9 | Monitor X Origin | rw | DDC/CI Capabilities | X origin in virtual screen (multi‑display). |
| 0xBA | Monitor Y Origin | rw | DDC/CI Capabilities | Y origin in virtual screen. |
| 0xBB | Header Error Count | rw | DDC/CI Capabilities | DPVL header error counter (saturates at FFFFh). |
| 0xBC | Body CRC Error Count | rw | DDC/CI Capabilities | DPVL body CRC error counter. |
| 0xBD | Client ID | rw | DDC/CI Capabilities | Assigned identification number (0000h‑FFFEh). |
| 0xBE | Link Control | rw | DDC/CI Capabilities | DPVL link shutdown enable/disable. |
| 0xC0 | Display Usage Time | ro | DDC/CI Capabilities | Accumulated active power‑on time in hours. |
| 0xC2 | Display Descriptor Length | ro | DDC/CI Capabilities | Length (bytes) of non‑volatile storage for display descriptor. |
| 0xC3 | Transmit Display Descriptor | rw | DDC/CI Capabilities | Write/read display descriptor (ISO 8859‑1 text). |
| 0xC4 | Enable Display of Display Descriptor | rw | DDC/CI Capabilities | Enable/disable showing descriptor when no video input. |
| 0xC7 | Display Enable Key | rw | DDC/CI Capabilities | Deprecated –  - It must NOT be implemented in new designs! |

### Display Controls
| 0x82 | Horizontal Mirror (Flip) | rw | Display Controls | Mirror image horizontally. |
| 0x84 | Vertical Mirror (Flip) | rw | Display Controls | Mirror image vertically. |
| 0x87 | Sharpness | rw | Display Controls | Adjust edge sharpness. |
| 0x88 | Velocity Scan Modulation | rw | Display Controls | Adjust velocity modulation of horizontal scan. |
| 0x8A | Color Saturation | rw | Display Controls | Adjust color saturation (amplitude of color difference). |
| 0x8B | TV‑Channel Up/Down | wo | Display Controls | Increment/decrement TV channel. |
| 0x8C | TV‑Sharpness | rw | Display Controls | Adjust high‑frequency detail for TV inputs. |
| 0x8E | TV‑Contrast | rw | Display Controls | Adjust contrast for TV inputs. |
| 0x8F | Audio Treble | rw | Display Controls | Adjust treble (cut/boost). |
| 0x90 | Hue | rw | Display Controls | Adjust hue (tint) – shift towards red/blue. |
| 0x91 | Audio Bass | rw | Display Controls | Adjust bass (cut/boost). |
| 0x92 | TV‑Black Level / Luminance | rw | Display Controls | Adjust black level for TV inputs. |
| 0x93 | Audio Balance L/R | rw | Display Controls | Adjust left‑right balance. |
| 0x94 | Audio Processor Mode | rw | Display Controls | Select audio processing mode (mono, stereo, Dolby, SRS, THX). |
| 0x95 | Window Position (TL_X) | rw | Display Controls | Top‑left X coordinate of window. |
| 0x96 | Window Position (TL_Y) | rw | Display Controls | Top‑left Y coordinate. |
| 0x97 | Window Position (BR_X) | rw | Display Controls | Bottom‑right X coordinate. |
| 0x98 | Window Position (BR_Y) | rw | Display Controls | Bottom‑right Y coordinate. |
| 0x9A | Window Background | rw | Display Controls | Adjust contrast between window and desktop. |
| 0x9B | 6 Axis Hue Control: Red | rw | Display Controls | Adjust red hue (7Fh = nominal). |
| 0x9C | 6 Axis Hue Control: Yellow | rw | Display Controls | Adjust yellow hue. |
| 0x9D | 6 Axis Hue Control: Green | rw | Display Controls | Adjust green hue. |
| 0x9E | 6 Axis Hue Control: Cyan | rw | Display Controls | Adjust cyan hue. |
| 0x9F | 6 Axis Hue Control: Blue | rw | Display Controls | Adjust blue hue. |
| 0xA2 | Auto Setup On/Off | wo | Display Controls | Enable/disable periodic auto setup. |
| 0xA4 | Window Mask Control | rw | Display Controls | Mask windows and set coordinates (legacy and new). |
| 0xA5 | Window Select | rw | Display Controls | Select active window (1‑7) or full image area. |
| 0xA6 | Window Size | rw | Display Controls | Adjust size of selected window. |
| 0xA7 | Window Transparency | rw | Display Controls | Adjust transparency of selected window. |
| 0xAA | Screen Orientation | ro | Display Controls | Return screen orientation (0°, 90°, 180°, 270°). |
| 0xCD | Status Indicators (Host) | rw | Display Controls | Control up to 16 LED indicators for host status (power, HDD, email, etc.). |
| 0xCE | Auxiliary Display Size | ro | Display Controls | Return rows and columns of auxiliary alphanumeric display. |
| 0xCF | Auxiliary Display Data | wo | Display Controls | Write text to auxiliary display. |
| 0xD0 | Output Select | rw | Display Controls | Select output source (similar to Input Select). |
| 0xD2 | Asset Tag | rw | Display Controls | Read/write asset tag (16 bytes, with key protection). |
| 0xD4 | Stereo Video Mode | rw | Display Controls | Select 2D/3D video mode (field‑sequential, interleaved, etc.). |
| 0xD7 | Auxiliary Power Output | rw | Display Controls | Enable/disable auxiliary power output to host. |
| 0xDA | Scan Mode | rw | Display Controls | Control scan characteristics (TV applications). |
| 0xDB | Image Mode | rw | Display Controls | Select image mode (Full, Zoom, Squeeze, Variable). |
| 0xDE | Scratch Pad | rw | Display Controls | Volatile storage (2 bytes) for software use, cleared on power‑on. |

### Image Adjustment
| 0x0B | User Color Temperature Increment | ro | Image Adjustment | Minimum increment for user color temperature adjustment. |
| 0x0E | Clock | rw | Image Adjustment | Adjust video sampling clock frequency. |
| 0x17 | User Color Vision Compensation | rw | Image Adjustment | Compensate for red‑color deficiency. |
| 0x1C | Focus | rw | Image Adjustment | Adjust image focus. |
| 0x1E | Auto Setup | rw | Image Adjustment | Perform auto setup (H/V position, clock, phase, etc.). |
| 0x1F | Auto Color Setup | rw | Image Adjustment | Perform auto color setup (gain, offset, A/D). |
| 0x22 | Horizontal Size | rw | Image Adjustment | Adjust image width. |
| 0x24 | Horizontal Pincushion | rw | Image Adjustment | Adjust horizontal pincushion distortion. |
| 0x26 | Horizontal Pincushion Balance | rw | Image Adjustment | Shift center section left/right. |
| 0x28 | Horizontal Convergence R/B | rw | Image Adjustment | Shift red/blue pixels horizontally relative to green. |
| 0x29 | Horizontal Convergence M/G | rw | Image Adjustment | Shift magenta/green horizontally. |
| 0x2A | Horizontal Linearity | rw | Image Adjustment | Adjust pixel density in center. |
| 0x2C | Horizontal Linearity Balance | rw | Image Adjustment | Shift pixel density left/right. |
| 0x2E | Gray Scale Expansion | rw | Image Adjustment | Expand gray scale in near‑white and/or near‑black regions. |
| 0x30 | Vertical Position (Phase) | rw | Image Adjustment | Move image up/down. |
| 0x32 | Vertical Size | rw | Image Adjustment | Adjust image height. |
| 0x34 | Vertical Pincushion | rw | Image Adjustment | Adjust vertical pincushion distortion. |
| 0x36 | Vertical Pincushion Balance | rw | Image Adjustment | Shift center section up/down. |
| 0x38 | Vertical Convergence R/B | rw | Image Adjustment | Shift red/blue pixels vertically. |
| 0x39 | Vertical Convergence M/G | rw | Image Adjustment | Shift magenta/green vertically. |
| 0x3A | Vertical Linearity | rw | Image Adjustment | Adjust scan line density in center. |
| 0x3C | Vertical Linearity Balance | rw | Image Adjustment | Shift scan line density top/bottom. |
| 0x3E | Clock Phase | rw | Image Adjustment | Adjust sampling clock phase. |
| 0x40 | Horizontal Parallelogram | rw | Image Adjustment | Shift top section left/right relative to bottom. |
| 0x41 | Vertical Parallelogram | rw | Image Adjustment | Shift top section left/right. |
| 0x42 | Horizontal Keystone | rw | Image Adjustment | Adjust horizontal keystone (top vs bottom width). |
| 0x43 | Vertical Keystone | rw | Image Adjustment | Adjust vertical keystone (left vs right height). |
| 0x44 | Rotation | rw | Image Adjustment | Rotate image clockwise/counter‑clockwise. |
| 0x46 | Top Corner Flare | rw | Image Adjustment | Adjust distance between left/right sides at top. |
| 0x48 | Top Corner Hook | rw | Image Adjustment | Move top of image left/right. |
| 0x4A | Bottom Corner Flare | rw | Image Adjustment | Adjust distance between left/right sides at bottom. |
| 0x4C | Bottom Corner Hook | rw | Image Adjustment | Move bottom of image left/right. |
| 0x54 | Performance Preservation | rw | Image Adjustment | Control image‑burn‑in prevention features (orbiting, etc.). |
| 0x5A | 6 Axis Saturation Control: Yellow | rw | Image Adjustment | Adjust yellow saturation. |
| 0x5C | 6 Axis Saturation Control: Cyan | rw | Image Adjustment | Adjust cyan saturation. |
| 0x5D | 6 Axis Saturation Control: Blue | rw | Image Adjustment | Adjust blue saturation. |
| 0x5E | 6 Axis Saturation Control: Magenta | rw | Image Adjustment | Adjust magenta saturation. |
| 0x66 | Ambient Light Sensor | rw | Image Adjustment | Enable/disable ambient light sensor. |
| 0x6D | Backlight Level: Red | rw | Image Adjustment | Adjust red backlight level. |
| 0x6E | Video Black Level: Green | rw | Image Adjustment | Adjust green black level. |
| 0x6F | Backlight Level: Green | rw | Image Adjustment | Adjust green backlight level. |
| 0x70 | Video Black Level: Blue | rw | Image Adjustment | Adjust blue black level. |

### Manufacturer Specific
| 0xE0 | Manufacturer Specific E0 | rw | Manufacturer Specific | OEM‑defined control. |
| 0xE3 | Manufacturer Specific E3 | rw | Manufacturer Specific | OEM‑defined control. |
| 0xE4 | Manufacturer Specific E4 | rw | Manufacturer Specific | OEM‑defined control. |
| 0xE5 | Manufacturer Specific E5 | rw | Manufacturer Specific | OEM‑defined control. |
| 0xE6 | Manufacturer Specific E6 | rw | Manufacturer Specific | OEM‑defined control. |
| 0xE7 | Manufacturer Specific E7 | rw | Manufacturer Specific | OEM‑defined control. |
| 0xE8 | Manufacturer Specific E8 | rw | Manufacturer Specific | OEM‑defined control. |
| 0xE9 | Manufacturer Specific E9 | rw | Manufacturer Specific | OEM‑defined control. |
| 0xEA | Manufacturer Specific EA | rw | Manufacturer Specific | OEM‑defined control. |
| 0xEB | Manufacturer Specific EB | rw | Manufacturer Specific | OEM‑defined control. |
| 0xEC | Manufacturer Specific EC | rw | Manufacturer Specific | OEM‑defined control. |
| 0xED | Manufacturer Specific ED | rw | Manufacturer Specific | OEM‑defined control. |
| 0xEE | Manufacturer Specific EE | rw | Manufacturer Specific | OEM‑defined control. |
| 0xEF | Manufacturer Specific EF | rw | Manufacturer Specific | OEM‑defined control. |
| 0xF0 | Manufacturer Specific F0 | rw | Manufacturer Specific | OEM‑defined control. |
| 0xF1 | Manufacturer Specific F1 | rw | Manufacturer Specific | OEM‑defined control. |
| 0xF2 | Manufacturer Specific F2 | rw | Manufacturer Specific | OEM‑defined control. |
| 0xF3 | Manufacturer Specific F3 | rw | Manufacturer Specific | OEM‑defined control. |
| 0xF4 | Manufacturer Specific F4 | rw | Manufacturer Specific | OEM‑defined control. |
| 0xF5 | Manufacturer Specific F5 | rw | Manufacturer Specific | OEM‑defined control. |
| 0xF6 | Manufacturer Specific F6 | rw | Manufacturer Specific | OEM‑defined control. |
| 0xF7 | Manufacturer Specific F7 | rw | Manufacturer Specific | OEM‑defined control. |
| 0xF9 | Manufacturer Specific F9 | rw | Manufacturer Specific | OEM‑defined control. |
| 0xFA | Manufacturer Specific FA | rw | Manufacturer Specific | OEM‑defined control. |
| 0xFB | Manufacturer Specific FB | rw | Manufacturer Specific | OEM‑defined control. |
| 0xFC | Manufacturer Specific FC | rw | Manufacturer Specific | OEM‑defined control. |
| 0xFE | Manufacturer Specific FE | rw | Manufacturer Specific | OEM‑defined control. |

### Preset Operations
| 0x00 | Code Page | rw | Preset Operations | Read/write the active code page ID. Default is 00h. |
| 0x01 | Degauss | wo | Preset Operations | Perform CRT degauss cycle. |
| 0x03 | Soft Controls | ro | Preset Operations | Read active button (soft buttons, power, brightness, etc.). |
| 0x06 | Restore Factory Geometry Defaults | wo | Preset Operations | Restore factory defaults for geometry adjustments. |
| 0x0A | Restore Factory TV Defaults | wo | Preset Operations | Restore factory defaults for TV functions. |
| 0xB0 | Settings | wo | Preset Operations | Store current settings (01h) or restore factory/user defaults (02h). |

## Summary by Category
| Category | Supported | Not Supported | Total |
|----------|-----------|---------------|-------|
| DDC/CI Capabilities | 9 | 18 | 27 |
| Display Controls | 8 | 40 | 48 |
| Image Adjustment | 25 | 42 | 67 |
| Manufacturer Specific | 5 | 27 | 32 |
| Preset Operations | 4 | 6 | 10 |
| **Total** | **51** | **133** | **184** |
