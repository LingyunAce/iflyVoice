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

板子和 Windows 本机至少通过以下方式之一连接（两路可同时用）：
- **以太网 SSH**：板子 IP `192.168.1.207`
- **USB Type-C RNDIS**：板子 IP `169.254.184.100`（开机自启，插线即用）
- 用户名 `cat`，密码见 `~/.openclaw/board_creds.json`

## 自动检测连接方式

使用 `exec` 工具执行以下检测脚本（Windows PowerShell）：

```powershell
# 1. USB RNDIS（优先——插线即用）
if (Test-Connection 169.254.184.100 -Count 1 -Quiet) { echo "USB_RNDIS:169.254.184.100" }

# 2. 以太网 SSH
if (Test-Connection 192.168.1.207 -Count 1 -Quiet) { echo "ETH_SSH:192.168.1.207" }

# 3. 扫描其他可能 IP
foreach ($ip in @("192.168.137.2","169.254.1.2","10.0.0.2")) {
  if (Test-Connection $ip -Count 1 -Quiet) { echo "OTHER:$ip"; break }
}
```

## 列出板子文件

```bash
# USB RNDIS（优先）
plink -batch -pw $BOARD_PASSWORD cat@169.254.184.100 "ls -la ~/.openclaw/canvas/; ls -la ~/.openclaw/workspace/"

# 以太网（备用）
plink -batch -pw $BOARD_PASSWORD cat@192.168.1.207 "ls -la ~/.openclaw/canvas/"
```

## 拷贝文件到本机

```bash
# USB RNDIS（优先）— 拷贝到 Windows
pscp -batch -pw $BOARD_PASSWORD cat@169.254.184.100:.openclaw/canvas/<文件名> "D:\AI\project\iflyVoice\downloads\"

# 以太网（备用）
pscp -batch -pw $BOARD_PASSWORD cat@192.168.1.207:.openclaw/canvas/<文件名> "D:\AI\project\iflyVoice\downloads\"

# 含有 host key 的完整命令（避免首次确认）
plink -batch -pw $BOARD_PASSWORD -hostkey "ssh-ed25519 255 SHA256:XIN5KVFAwNkKgi2A2uZ2reFncd0ka30s/1FoXEycj28" cat@169.254.184.100 "ls ~/.openclaw/canvas/"
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
