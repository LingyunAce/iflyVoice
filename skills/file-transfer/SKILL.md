---
name: file-transfer
description: "RK3576 板子 ↔ Windows 本机文件传输。USB RNDIS 优先（插线即用），以太网备用。"
---

# 文件传输 — RK3576 ↔ Windows

**核心原则：PC 拉，不是板子推。**

板子 SSH server 始终开着。PC 用 `pscp` 从板子下载文件，一行命令搞定。
板子不需要往 PC 推——PC 不需要开任何端口或服务。不要自己发明 HTTP/FTP 方案。

`pscp` 已在 Windows 本机安装（PuTTY 套件），板子的 SSH 端口 22 始终可用。

即插即用，不要绕路。

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

## 直接执行（不要分析，照做）

用户要求传输文件时，直接用 exec 执行以下命令。**不要解释、不要发明替代方案。**

### 拷贝：板子 → PC

```batch
powershell -Command "if (Test-Connection 169.254.184.100 -Count 1 -Quiet) { $ip='169.254.184.100' } else { $ip='192.168.1.207' }; pscp -batch -pw temppwd -hostkey ""ssh-ed25519 255 SHA256:XIN5KVFAwNkKgi2A2uZ2reFncd0ka30s/1FoXEycj28"" cat@${ip}:.openclaw/canvas/<文件名> D:\AI\project\iflyVoice\downloads\"
```

### 列出文件

```batch
plink -batch -pw temppwd -hostkey "ssh-ed25519 255 SHA256:XIN5KVFAwNkKgi2A2uZ2reFncd0ka30s/1FoXEycj28" cat@169.254.184.100 "ls -la ~/.openclaw/canvas/; echo '---workspace---'; ls -p ~/.openclaw/workspace/ | grep -v '/$'"
```

USB 不通自动切以太网。一行搞定。
