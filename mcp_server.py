#!/usr/bin/env python3
"""MCP server — exposes iflyVoice tools to OpenClaw via Model Context Protocol (stdio).

OpenClaw connects via stdio JSON-RPC and can call tools directly without exec+curl.
Usage: python3 mcp_server.py
"""
from __future__ import annotations
import json
import sys
import urllib.request
import urllib.error

IFLYVOICE = "http://127.0.0.1:18766"
API_KEY = ""  # not needed for localhost

# ── Tool definitions ─────────────────────────────────────────
TOOLS = [
    {
        "name": "set_brightness",
        "description": "设置显示器亮度 (0-100)。DDC/CI 真实硬件控制。",
        "inputSchema": {
            "type": "object",
            "properties": {
                "value": {"type": "integer", "description": "亮度值 0-100", "minimum": 0, "maximum": 100},
            },
            "required": ["value"],
        },
    },
    {
        "name": "adjust_brightness",
        "description": "调整显示器亮度（增量，正数为调亮，负数为调暗）",
        "inputSchema": {
            "type": "object",
            "properties": {
                "delta": {"type": "integer", "description": "亮度变化量"},
            },
            "required": ["delta"],
        },
    },
    {
        "name": "set_contrast",
        "description": "设置显示器对比度 (0-100)。DDC/CI 真实硬件控制。",
        "inputSchema": {
            "type": "object",
            "properties": {
                "value": {"type": "integer", "description": "对比度值 0-100", "minimum": 0, "maximum": 100},
            },
            "required": ["value"],
        },
    },
    {
        "name": "set_volume",
        "description": "设置系统音量 (0-100)",
        "inputSchema": {
            "type": "object",
            "properties": {
                "value": {"type": "integer", "description": "音量值 0-100", "minimum": 0, "maximum": 100},
            },
            "required": ["value"],
        },
    },
    {
        "name": "adjust_volume",
        "description": "调整系统音量（增量）",
        "inputSchema": {
            "type": "object",
            "properties": {
                "delta": {"type": "integer", "description": "音量变化量"},
            },
            "required": ["delta"],
        },
    },
    {
        "name": "set_input",
        "description": "切换显示器输入源。可用代码: 0f=DisplayPort-1, 10=DisplayPort-2, 11=HDMI-1",
        "inputSchema": {
            "type": "object",
            "properties": {
                "code": {"type": "string", "description": "输入源 hex 代码"},
            },
            "required": ["code"],
        },
    },
    {
        "name": "list_inputs",
        "description": "列出显示器可用输入源（DDC/CI 探测 + xrandr 输出）",
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "list_apps",
        "description": "列出当前运行的桌面应用",
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "launch_app",
        "description": "启动桌面应用",
        "inputSchema": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "应用名称，如 firefox"},
            },
            "required": ["name"],
        },
    },
    {
        "name": "close_app",
        "description": "关闭桌面应用",
        "inputSchema": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "应用名称"},
            },
            "required": ["name"],
        },
    },
    {
        "name": "focus_app",
        "description": "聚焦/切换到指定桌面应用",
        "inputSchema": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "应用名称"},
            },
            "required": ["name"],
        },
    },
    {
        "name": "stt_transcribe",
        "description": "语音转文字 (SenseVoiceSmall)。上传音频文件路径进行识别。",
        "inputSchema": {
            "type": "object",
            "properties": {
                "file": {"type": "string", "description": "音频文件路径"},
            },
            "required": ["file"],
        },
    },
    {
        "name": "list_vcp_codes",
        "description": "查询 VESA VCP 码表定义",
        "inputSchema": {
            "type": "object",
            "properties": {
                "keyword": {"type": "string", "description": "按关键词搜索"},
            },
        },
    },
]


def call_iflyvoice(tool_name: str, params: dict) -> dict:
    """Call iflyVoice HTTP API and return result."""
    url = f"{IFLYVOICE}/api/v1/tools/{tool_name}"
    data = json.dumps(params).encode()
    req = urllib.request.Request(
        url, data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        return {"ok": False, "err": f"HTTP {e.code}: {e.reason}"}
    except Exception as e:
        return {"ok": False, "err": str(e)}


def handle_request(req: dict) -> dict | None:
    """Handle a single JSON-RPC request. Returns response or None for notifications."""
    method = req.get("method", "")
    rid = req.get("id")

    if method == "initialize":
        return {
            "jsonrpc": "2.0", "id": rid,
            "result": {
                "protocolVersion": "2024-11-05",
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "iflyvoice-mcp", "version": "1.0.0"},
            },
        }

    if method == "notifications/initialized":
        return None  # notification, no response

    if method == "tools/list":
        return {
            "jsonrpc": "2.0", "id": rid,
            "result": {"tools": TOOLS},
        }

    if method == "tools/call":
        tool_name = req["params"]["name"]
        arguments = req["params"].get("arguments", {})
        # Map tool name to iflyVoice endpoint
        result = call_iflyvoice(tool_name, arguments)
        return {
            "jsonrpc": "2.0", "id": rid,
            "result": {"content": [{"type": "text", "text": json.dumps(result, ensure_ascii=False)}]},
        }

    if method == "ping":
        return {"jsonrpc": "2.0", "id": rid, "result": {}}

    return {
        "jsonrpc": "2.0", "id": rid,
        "error": {"code": -32601, "message": f"Method not found: {method}"},
    }


def main():
    """Main stdio loop."""
    # Log to stderr so stdout stays clean for JSON-RPC
    print("[mcp] iflyVoice MCP server started", file=sys.stderr, flush=True)

    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            req = json.loads(line)
            resp = handle_request(req)
            if resp is not None:
                sys.stdout.write(json.dumps(resp, ensure_ascii=False) + "\n")
                sys.stdout.flush()
        except json.JSONDecodeError as e:
            print(f"[mcp] JSON error: {e}", file=sys.stderr)
        except Exception as e:
            print(f"[mcp] Error: {e}", file=sys.stderr)


if __name__ == "__main__":
    main()
