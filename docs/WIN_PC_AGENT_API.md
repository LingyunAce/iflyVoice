# Win PC Agent HTTP API 契约 (v0.1)

> **状态**：Draft — Plan 1 仅写契约，**实现放下一期**。
> RK3576 端 `executor/pc_agent.py` 按本契约调用。
> Win PC 端用 Python+pywin32 实现 agent.exe（HTTP 服务 + 现有 DDC-CI / app_manager / B 站代码）。

## 通用约定

- **协议**：HTTP/1.1，端口默认 `18770`
- **Content-Type**: `application/json; charset=utf-8`
- **字符集**: UTF-8
- **超时**: 3s（executor 内部用 `tenacity` 重试 3 次：1s/2s/4s 退避）

## 统一响应格式

成功：
```json
{"ok": true, "data": {...}}
```

失败：
```json
{"ok": false, "err": "人类可读错误描述", "code": "ERR_XXX"}
```

错误码：
- `ERR_DISPLAY_NOT_FOUND` — 找不到指定显示器
- `ERR_DDCCI_UNSUPPORTED` — 显示器不支持 DDC-CI
- `ERR_APP_NOT_FOUND` — 找不到应用
- `ERR_APP_LAUNCH_FAILED` — 启动应用失败
- `ERR_BILIBILI_API_FAILED` — B 站 API 调用失败
- `ERR_INTERNAL` — 内部错误

## 端点

### 健康检查

`GET /health`

响应：
```json
{"ok": true, "version": "0.1.0"}
```

### 显示器枚举

`GET /monitors`

响应：
```json
{
  "ok": true,
  "data": {
    "monitors": [
      {"index": 0, "name": "DELL U2723QE", "supports_ddcci": true, "current_input": "HDMI1"}
    ]
  }
}
```

### 显示器控制

| 方法 | 路径 | 请求体 | 响应 data |
|------|------|--------|-----------|
| POST | `/display/brightness` | `{"value": 0-100}` | `{"actual": 50, "restored": false}` |
| POST | `/display/contrast` | `{"value": 0-100}` | `{"actual": 50}` |
| POST | `/display/color_temp` | `{"value": 0-100, "monitor_index": 0}` | `{"actual": 50}` |
| GET | `/display/color_temp` | - | `{"value": 50}` |
| GET | `/display/inputs` | `?monitor_index=0` | `{"current": "HDMI1", "supported": [{"code": 17, "name": "HDMI1"}, ...]}` |
| POST | `/display/input` | `{"code": 17, "monitor_index": 0}` | `{"name": "HDMI1", "old_name": "DP1", "restored": false}` |

### 音量

| 方法 | 路径 | 请求体 | 响应 data |
|------|------|--------|-----------|
| GET | `/volume` | - | `{"value": 50}` |
| POST | `/volume` | `{"value": 0-100}` | `{"actual": 50}` |

### 桌面应用

| 方法 | 路径 | 请求体 | 响应 data |
|------|------|--------|-----------|
| GET | `/apps/installed` | - | `{"apps": [{"name": "微信", "path": "..."}]}` |
| GET | `/apps/running` | - | `{"windows": [{"hwnd": 12345, "title": "微信", "pid": 6789}]}` |
| POST | `/apps/launch` | `{"name": "微信"}` | `{"pid": 6789}` |
| POST | `/apps/close` | `{"name": "微信"}` 或 `{"hwnd": 12345}` | `{}` |
| POST | `/apps/focus` | `{"name": "微信"}` 或 `{"hwnd": 12345}` | `{}` |

### B 站

| 方法 | 路径 | 请求体 | 响应 data |
|------|------|--------|-----------|
| GET | `/bilibili/search` | `?keyword=Python 教程` | `{"results": [{"bvid": "BV1xx", "title": "...", "author": "...", "duration": 600}]}` |
| POST | `/bilibili/play` | `{"bvid": "BV1xx"}` | `{"title": "..."}` |

## 安全

- 内网使用，无需鉴权（v0.1）
- v0.2 加 `Authorization: Bearer <token>` 头

## 版本

- v0.1: 2026-06-17 初稿
