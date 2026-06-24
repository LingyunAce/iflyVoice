---
name: file-transfer
description: "RK3576 板子 ↔ Windows 本机文件传输。USB RNDIS 优先（插线即用），以太网备用。"
---

# 文件传输 — RK3576 ↔ Windows

即插即用文件传输。全程 exec 命令行，无需交互。

## 连接配置

| 方式 | IP | 密码 | Host Key |
|------|-----|------|----------|
| USB RNDIS（优先） | 169.254.184.100 | `temppwd` | `ssh-ed25519 255 SHA256:XIN5KVFAwNkKgi2A2uZ2reFncd0ka30s/1FoXEycj28` |
| 以太网（备用） | 192.168.1.207 | 同上 | 同上 |

用户 `cat`，目标目录 `D:\AI\project\iflyVoice\downloads\`。

## 标准操作流程

### 步骤 0：准备连接参数

```bash
BOARD_IP=169.254.184.100
BOARD_PW=temppwd
HK="ssh-ed25519 255 SHA256:XIN5KVFAwNkKgi2A2uZ2reFncd0ka30s/1FoXEycj28"
```

### 步骤 1：检测连接

```bash
# 先试 USB
ping -n 1 169.254.184.100 >nul 2>&1 && echo "USB_OK" && set BOARD_IP=169.254.184.100 || (
  # USB 不通，试以太网
  ping -n 1 192.168.1.207 >nul 2>&1 && echo "ETH_OK" && set BOARD_IP=192.168.1.207 || (
    echo "NOT_CONNECTED" && exit 1
  )
)
```

### 步骤 2：列出板子文件

```bash
plink -batch -pw %BOARD_PW% -hostkey "%HK%" cat@%BOARD_IP% "ls -la ~/.openclaw/canvas/ 2>/dev/null; echo '---workspace---'; ls -p ~/.openclaw/workspace/ 2>/dev/null | grep -v '/$'"
```

### 步骤 3：拷贝文件

```bash
pscp -batch -pw %BOARD_PW% -hostkey "%HK%" cat@%BOARD_IP%:.openclaw/canvas/<文件名> "D:\AI\project\iflyVoice\downloads\"
```

### USB IP 修复（如 USB 不通）

```bash
# 通过以太网修复 USB IP
plink -batch -pw %BOARD_PW% -hostkey "%HK%" cat@192.168.1.207 "sudo ip addr add 169.254.184.100/16 dev usb0 2>/dev/null; ip -br addr show usb0"
```

## 板子常用路径

| 路径 | 内容 |
|------|------|
| `~/.openclaw/canvas/` | OpenClaw 生成的文档/PPT/HTML |
| `~/.openclaw/workspace/` | OpenClaw 项目文件 |
| `~/iflyVoice/` | iflyVoice 代码 |

## 完整操作示例

用户说："把板子上的 PPT 文件拷到本机"

执行：
```bash
# 1. 检测
ping -n 1 169.254.184.100 >nul 2>&1 && echo "USB: OK" || echo "USB: FAIL"

# 2. 列表
plink -batch -pw temppwd -hostkey "ssh-ed25519 255 SHA256:XIN5KVFAwNkKgi2A2uZ2reFncd0ka30s/1FoXEycj28" cat@169.254.184.100 "ls -la ~/.openclaw/canvas/"

# 3. 拷贝
pscp -batch -pw temppwd -hostkey "ssh-ed25519 255 SHA256:XIN5KVFAwNkKgi2A2uZ2reFncd0ka30s/1FoXEycj28" cat@169.254.184.100:.openclaw/canvas/ai-display-ppt.pptx "D:\AI\project\iflyVoice\downloads\"
```
