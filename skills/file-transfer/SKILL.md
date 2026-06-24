---
name: file-transfer
description: "RK3576 板子 ↔ Windows 本机文件传输。自动检测连接方式（SSH/USB），列出板子文件，拷贝到本机。"
---

# 文件传输 — RK3576 ↔ Windows

在 RK3576 板子和 Windows 本机之间传输文件。自动检测连接方式并选择最优路径。

## 密码获取

板子密码存储在板子本地 `~/.openclaw/board_creds.json`，使用前先读取：

```bash
plink -batch -pw <password> cat@<ip> "cat ~/.openclaw/board_creds.json"
```

`BOARD_PASSWORD` 环境变量在以下命令中代表该密码。Windows 本机也可在 `D:\AI\project\iflyVoice\.board_creds` 文件中存储密码（不提交 git）。

## 前置条件

板子和 Windows 本机至少通过以下方式之一连接：
- **SSH**：板子 IP 通常为 192.168.1.207，用户名 cat（密码见 `~/.openclaw/board_creds.json`）
- **USB 直连**：板子作为 USB gadget（RNDIS/ECM），IP 通常为 192.168.137.x 或 169.254.x.x

## 自动检测连接方式

使用 `exec` 工具执行以下检测脚本：

```bash
# 1. 先试 SSH
ping -n 1 192.168.1.207 >nul 2>&1 && echo "SSH_AVAILABLE" || echo "SSH_NOT_FOUND"

# 2. 再扫描 USB gadget IP
for ip in 192.168.137.2 192.168.137.1 169.254.1.2 10.0.0.2; do
  ping -n 1 -w 500 $ip >nul 2>&1 && echo "USB_GADGET:$ip" && break
done

# 3. Windows 检测 USB 设备
pnputil /enum-devices 2>nul | findstr /i "rk3576\|rockchip\|gadget\|rndis" && echo "USB_DEVICE_FOUND"
```

## 列出板子文件

```bash
# SSH 方式
plink -batch -pw $BOARD_PASSWORD cat@192.168.1.207 "ls -la ~/.openclaw/canvas/; echo '---'; ls -la ~/.openclaw/workspace/ | grep -v '^d\|\.git'"

# USB gadget 方式
plink -batch -pw $BOARD_PASSWORD cat@<usb_ip> "ls -la ~/.openclaw/canvas/"
```

## 拷贝文件到本机

```bash
# SSH 方式 — 单个文件
pscp -batch -pw $BOARD_PASSWORD cat@192.168.1.207:.openclaw/canvas/<文件名> "<Windows本地路径>"

# SSH 方式 — 整个目录
pscp -batch -pw $BOARD_PASSWORD cat@192.168.1.207:.openclaw/canvas/* "<Windows本地路径>\"

# USB gadget 方式 — IP 换成检测到的 USB IP
pscp -batch -pw $BOARD_PASSWORD cat@<usb_ip>:.openclaw/canvas/<文件名> "<Windows本地路径>"
```

## 常用板子路径

| 路径 | 内容 |
|------|------|
| `~/.openclaw/canvas/` | OpenClaw 生成的文档/PPT/HTML |
| `~/.openclaw/workspace/` | OpenClaw workspace 文件 |
| `~/.openclaw/workspace/memory/` | OpenClaw 记忆文件 |
| `~/iflyVoice/` | iflyVoice 项目代码 |

## 操作流程

1. 先自动检测连接方式
2. 用户指定"列出文件"或"拷贝 XXX 文件到本机"
3. 根据检测到的连接方式选择对应命令
4. 执行并报告结果

## 注意事项

- 板子密码为 `temppwd`，用户名 `cat`
- 拷贝到本机的默认路径为 `D:\AI\project\iflyVoice\downloads\`
- 如果 SSH 和 USB 都通，优先用 USB（速度快）
