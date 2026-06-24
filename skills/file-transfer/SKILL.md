---
name: file-transfer
description: "RK3576 板子 ↔ Windows 本机文件传输。USB RNDIS 优先（插线即用），以太网备用。"
---

# 文件传输 — RK3576 ↔ Windows

即插即用文件传输。全程 exec 命令行，无需交互。

## 连接参数

用户 `cat`，密码 `temppwd`，目标目录 `D:\AI\project\iflyVoice\downloads\`。
Host Key: `ssh-ed25519 255 SHA256:XIN5KVFAwNkKgi2A2uZ2reFncd0ka30s/1FoXEycj28`

IP 不固定——通过自动检测获取。

## 标准操作流程

### 步骤 1：检测连接（动态 IP）

执行 PowerShell 检测脚本：

```powershell
powershell -File "D:\AI\project\iflyVoice\skills\file-transfer\detect_board.ps1"
```

脚本自动完成（USB 优先）：
- 找 RNDIS 网卡 → 推导板子 IP → 扫描 .2-.10
- USB 静态 IP 兜底 (169.254.184.100 等)
- 以太网最后尝试 (192.168.1.207)

结果写入 `board_connection.json`，包含 `method`、`ip`、`user`、`password`。

### 步骤 2：读取 IP

```bash
# 从 JSON 提取 IP
set BOARD_IP=<从 board_connection.json 读取>
set BOARD_PW=temppwd
set HK="ssh-ed25519 255 SHA256:XIN5KVFAwNkKgi2A2uZ2reFncd0ka30s/1FoXEycj28"
```

### 步骤 3：列出文件

```bash
plink -batch -pw %BOARD_PW% -hostkey "%HK%" cat@%BOARD_IP% "ls -la ~/.openclaw/canvas/"
```

### 步骤 4：拷贝文件

```bash
pscp -batch -pw %BOARD_PW% -hostkey "%HK%" cat@%BOARD_IP%:.openclaw/canvas/<文件名> "D:\AI\project\iflyVoice\downloads\"
```

### USB IP 修复（仅 USB 不通时）

```bash
# 通过以太网给 usb0 配 IP
plink -batch -pw temppwd -hostkey "%HK%" cat@192.168.1.207 "sudo dhclient usb0 2>/dev/null || sudo ip addr add 169.254.184.100/16 dev usb0"
```

## 板子常用路径

| 路径 | 内容 |
|------|------|
| `~/.openclaw/canvas/` | 生成的文档/PPT/HTML |
| `~/.openclaw/workspace/` | 项目文件 |
| `~/iflyVoice/` | iflyVoice 代码 |

## 完整示例

用户说："把板子上的 PPT 拷到本机"

```bash
# 1. 检测
powershell -File "D:\AI\project\iflyVoice\skills\file-transfer\detect_board.ps1"

# 2. 根据检测结果执行（假设 USB 检测到 169.254.184.100）
pscp -batch -pw temppwd -hostkey "ssh-ed25519 255 SHA256:XIN5KVFAwNkKgi2A2uZ2reFncd0ka30s/1FoXEycj28" cat@169.254.184.100:.openclaw/canvas/ai-display-ppt.pptx "D:\AI\project\iflyVoice\downloads\"
```
