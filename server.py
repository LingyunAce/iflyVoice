#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Ollama Local Proxy Server v3 — with system tray support
"""
import os, sys, json, socket, threading
from http.server import HTTPServer, BaseHTTPRequestHandler
from socketserver import ThreadingMixIn

OLLAMA_HOST = "192.168.1.32"
OLLAMA_PORT = 11434
_OLLAMA_CONFIG = {"host": OLLAMA_HOST, "port": OLLAMA_PORT}
LISTEN_PORT = 18766
STATIC_DIR = os.path.dirname(os.path.abspath(__file__)) or "."

def _log(msg):
    try:
        sys.stderr.write(msg + "\n")
    except Exception:
        pass

class ThreadedHTTPServer(ThreadingMixIn, HTTPServer):
    allow_reuse_address = True
    daemon_threads = True


class Handler(BaseHTTPRequestHandler):
    _native_state = {"colorTemp": 50, "gamma": 50, "volume": 50}
    _state_lock = threading.Lock()
    _state_file = os.path.join(STATIC_DIR, ".native_state.json")
    protocol_version = "HTTP/1.0"

    def log_message(self, fmt, *args):
        sys.stderr.write(f"[{self.log_date_time_string()}] {args[0]}\n")

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Content-Length", "0")
        self.end_headers()

    def do_GET(self):
        if self.path.startswith("/health"):
            self._send_json(200, {"ok": True, "version": "0.2.0-linux", "platform": "linux-aarch64"})
            return
        if self.path.startswith("/exit"):
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(b'{"msg":"exiting"}')
            import sys; sys.exit(0)
            return
        elif self.path.startswith("/api/v1/tools/"):
            self._handle_tool("GET")
        elif self.path.startswith("/config/"):
            self._handle_config("GET")
        elif self.path.startswith("/ollama/"):
            self._proxy("GET")
        elif self.path.startswith("/native/"):
            self._handle_native("GET")
        elif self.path.startswith("/v1/audio/speech"):
            self._handle_tts()
        else:
            self._serve_static()

    def do_POST(self):
        if self.path.startswith("/api/v1/tools/"):
            self._handle_tool("POST")
        elif self.path.startswith("/config/"):
            self._handle_config("POST")
        elif self.path.startswith("/ollama/"):
            self._proxy("POST")
        elif self.path.startswith("/native/"):
            self._handle_native("POST")
        elif self.path.startswith("/v1/audio/speech"):
            self._handle_tts()
        else:
            self.send_error(404)

    def _cors_headers(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Cache-Control", "no-cache")

    def _serve_static(self):
        from embedded_static import get_embedded, get_static_dir
        path = self.path.split("?")[0].split("#")[0]
        if path == "/":
            path = "/index.html"
        data = get_embedded(path.lstrip("/"))
        if data is not None:
            ext = os.path.splitext(path)[1].lower()
            ct = {
                ".html": "text/html; charset=utf-8",
                ".css": "text/css; charset=utf-8",
                ".js": "application/javascript; charset=utf-8",
                ".json": "application/json",
                ".png": "image/png",
                ".jpg": "image/jpeg",
                ".svg": "image/svg+xml",
                ".ico": "image/x-icon",
            }.get(ext, "application/octet-stream")
            self.send_response(200)
            self.send_header("Content-Type", ct)
            self.send_header("Content-Length", str(len(data)))
            self._cors_headers()
            self.end_headers()
            self.wfile.write(data)
            return
        # 文件系统回退：仅在 get_static_dir() 返回具体目录时启用
        static_dir = get_static_dir()
        if not static_dir:
            self.send_error(404, "Static file not found (embedded only)")
            return
        filepath = os.path.normpath(os.path.join(static_dir, path.lstrip("/")))
        base_dir = os.path.dirname(os.path.abspath(__file__))
        if not (filepath.startswith(base_dir) or filepath.startswith(static_dir)):
            self.send_error(403); return
        try:
            with open(filepath, "rb") as f:
                data = f.read()
        except FileNotFoundError:
            self.send_error(404); return
        except Exception as e:
            self.send_error(500, str(e)); return
        ext = os.path.splitext(filepath)[1].lower()
        ct = {
            ".html": "text/html; charset=utf-8",
            ".css": "text/css; charset=utf-8",
            ".js": "application/javascript; charset=utf-8",
            ".json": "application/json",
            ".png": "image/png",
            ".jpg": "image/jpeg",
            ".svg": "image/svg+xml",
            ".ico": "image/x-icon",
        }.get(ext, "application/octet-stream")
        self.send_response(200)
        self.send_header("Content-Type", ct)
        self.send_header("Content-Length", str(len(data)))
        self._cors_headers()
        self.end_headers()
        self.wfile.write(data)

    def _proxy(self, method):
        target_path = self.path.replace("/ollama/", "/", 1)
        body = None
        if method == "POST":
            cl = int(self.headers.get("Content-Length", 0))
            if cl > 0:
                try:
                    body = self.rfile.read(cl)
                except Exception as e:
                    self._send_error_json(400, f"Read error: {e}"); return
        sock = None
        try:
            sock = socket.create_connection((_OLLAMA_CONFIG["host"], _OLLAMA_CONFIG["port"]), timeout=10)
            sock.settimeout(120)   # 防止 recv 无限阻塞（模型首次加载最多等 120s）
            req_lines = [f"{method} {target_path} HTTP/1.0"]
            req_lines.append(f"Host: {_OLLAMA_CONFIG['host']}:{_OLLAMA_CONFIG['port']}")
            if body is not None:
                req_lines.append("Content-Type: application/json")
                req_lines.append(f"Content-Length: {len(body)}")
            req_lines.append("Connection: close")
            req_lines.append("")
            req_data = "\r\n".join(req_lines).encode() + (b"\r\n" if body is None else b"\r\n" + (body or b""))
            sock.sendall(req_data)
            status_line = self._sock_readline(sock)
            if not status_line:
                raise Exception("Empty response from Ollama")
            parts = status_line.split(" ", 2)
            code = int(parts[1]) if len(parts) >= 2 else 502
            resp_ct = "application/json"
            while True:
                hline = self._sock_readline(sock).strip()
                if not hline: break
                if hline.lower().startswith("content-type:"):
                    resp_ct = hline.split(":", 1)[1].strip()
            self.send_response(code)
            self.send_header("Content-Type", resp_ct)
            self._cors_headers()
            self.end_headers()
            while True:
                chunk = sock.recv(4096)
                if not chunk: break
                try:
                    self.wfile.write(chunk); self.wfile.flush()
                except (BrokenPipeError, ConnectionResetError, OSError):
                    break
        except ConnectionRefusedError:
            self._send_error_json(502, "Ollama not running (connection refused)")
        except socket.timeout:
            self._send_error_json(504, "Ollama connection timed out")
        except Exception as e:
            self._send_error_json(500, f"Proxy error: {e}")
        finally:
            if sock:
                try: sock.close()
                except Exception: pass

    def _sock_readline(self, sock):
        buf = b""
        while True:
            ch = sock.recv(1)
            if not ch: return buf.decode("utf-8", errors="replace")
            buf += ch
            if buf.endswith(b"\r\n"): return buf[:-2].decode("utf-8", errors="replace")

    def _handle_config(self, method):
        path = self.path.split("?")[0]
        endpoint = path.replace("/config/", "", 1).strip("/")
        body = {}
        if method == "POST":
            content_len = int(self.headers.get("Content-Length", 0))
            if content_len > 0: body = json.loads(self.rfile.read(content_len))
        if endpoint == "ollama" and method == "POST":
            host = body.get("host", ""); port = body.get("port", 11434); model = body.get("model", "qwen3-vl:4b")
            _OLLAMA_CONFIG["host"] = host; _OLLAMA_CONFIG["port"] = int(port)
            _log(f"[Config] Ollama updated: {host}:{port} model={model}")
            self._send_json(200, {"success": True, "host": host, "port": port, "model": model})
        elif endpoint == "displayType":
            try:
                if method == "GET":
                    with Handler._state_lock:
                        dt = Handler._native_state.get("displayType", "native")
                    self._send_json(200, {"success": True, "displayType": dt})
                elif method == "POST":
                    dt = body.get("displayType", "native")
                    with Handler._state_lock:
                        Handler._native_state["displayType"] = dt
                    Handler._save_state()
                    _log(f"[Config] displayType updated: {dt}")
                    self._send_json(200, {"success": True, "displayType": dt})
            except Exception as e:
                import traceback; _log(f"[Config] displayType error: {e}\n{traceback.format_exc()}\n")
                self._send_json(500, {"success": False, "error": str(e)})
        else:
            self._send_json(404, {"success": False, "error": f"Unknown config: {endpoint}"})

    SENSEVOICE_CONFIG = {"base_url": "http://192.168.1.32:9997", "api_key": "sk-86ccca26e58a8", "model": "SenseVoiceSmall"}

    def _handle_tts(self):
        """Proxy text-to-speech to CosyVoice2 at 192.168.1.32:9997/v1/audio/speech"""
        import urllib.request
        cfg = self.SENSEVOICE_CONFIG
        target_url = f"{cfg['base_url']}/v1/audio/speech"
        cl = int(self.headers.get("Content-Length", 0))
        if cl <= 0:
            return self._send_json(400, {"success": False, "error": "No request body"})
        try:
            original_body = self.rfile.read(cl)
            req = urllib.request.Request(
                target_url,
                data=original_body,
                headers={
                    "Authorization": f"Bearer {cfg['api_key']}",
                    "Content-Type": "application/json",
                },
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=60) as resp:
                resp_body = resp.read()
                ct = resp.headers.get("Content-Type", "audio/mpeg")
                self.send_response(200)
                self.send_header("Content-Type", ct)
                self.send_header("Content-Length", str(len(resp_body)))
                self._cors_headers()
                self.end_headers()
                self.wfile.write(resp_body)
        except urllib.error.HTTPError as e:
            err_body = e.read().decode("utf-8", errors="replace")
            _log(f"[TTS] HTTP {e.code}: {err_body[:200]}")
            self._send_json(502, {"success": False, "error": f"TTS {e.code}: {err_body[:200]}"})
        except Exception as e:
            _log(f"[TTS] Error: {e}")
            self._send_json(500, {"success": False, "error": str(e)})

    def _handle_native(self, method):
        """本机屏幕软调（Plan 1 stub，Plan 2 替换为 linux/backlight.py）"""
        path = self.path.split("?")[0]
        endpoint = path.replace("/native/", "", 1).strip("/")

        if endpoint == "backlight" and method == "GET":
            # Plan 1 stub
            self._send_json(200, {"ok": True, "data": {"value": 50, "note": "stub; Plan 2 用 /sys/class/backlight"}})
        elif endpoint == "backlight" and method == "POST":
            cl = int(self.headers.get("Content-Length", 0))
            try:
                body = json.loads(self.rfile.read(cl).decode("utf-8"))
            except (ValueError, UnicodeDecodeError) as e:
                _log(f"[/native/backlight] invalid JSON: {e}")
                self._send_json(400, {"ok": False, "err": f"invalid JSON body: {e}", "code": "ERR_INVALID_JSON"})
                return
            except Exception as e:
                _log(f"[/native/backlight] read body error: {e}")
                self._send_json(400, {"ok": False, "err": f"failed to read body: {e}", "code": "ERR_INVALID_JSON"})
                return
            if not isinstance(body, dict):
                _log(f"[/native/backlight] body is not a dict: {type(body).__name__}")
                self._send_json(400, {"ok": False, "err": "body must be a JSON object", "code": "ERR_INVALID_JSON"})
                return
            value = body.get("value", 50)
            try:
                value = int(value)
            except (TypeError, ValueError) as e:
                _log(f"[/native/backlight] invalid value: {value!r} ({e})")
                self._send_json(400, {"ok": False, "err": f"value must be an integer: {e}", "code": "ERR_INVALID_JSON"})
                return
            self._send_json(200, {"ok": True, "data": {"value": max(0, min(100, value)), "note": "stub"}})
        elif endpoint == "ping":
            self._send_json(200, {"ok": True, "data": {"pong": True}})
        else:
            self._send_json(404, {"ok": False, "err": f"unknown native endpoint: {endpoint}"})

    def _handle_tool(self, method):
        """OpenClaw 集成的 HTTP tool 端点。
        路径格式：/api/v1/tools/<tool_name>
        body：JSON dict（参数）
        返回：{"ok": bool, "data": {...}, "err": "...", "code": "..."}
        """
        path = self.path.split("?")[0]
        tool_name = path.replace("/api/v1/tools/", "", 1).strip("/")

        # 工具名 → IntentType 映射
        TOOL_TO_INTENT = {
            "set_brightness": ("SET_BRIGHTNESS", {"value": "value"}),
            "adjust_brightness": ("ADJUST_BRIGHTNESS", {"delta": "delta"}),
            "set_contrast": ("SET_CONTRAST", {"value": "value"}),
            "adjust_contrast": ("ADJUST_CONTRAST", {"delta": "delta"}),
            "set_volume": ("SET_VOLUME", {"value": "value"}),
            "adjust_volume": ("ADJUST_VOLUME", {"delta": "delta"}),
            "launch_app": ("LAUNCH_APP", {"name": "name"}),
            "close_app": ("CLOSE_APP", {"name": "name"}),
            "focus_app": ("FOCUS_APP", {"name": "name"}),
            "list_apps": ("LIST_APPS", {}),
            "list_monitors": ("LIST_INPUTS", {}),
            "list_inputs": ("LIST_INPUTS", {}),
            "set_input": ("SET_INPUT", {"code": "code"}),
            "list_vcp_codes": ("LIST_VCP_CODES", {"code": "code", "keyword": "keyword"}),
        }

        if tool_name not in TOOL_TO_INTENT:
            self._send_json(404, {"ok": False,
                                  "err": f"unknown tool: {tool_name}",
                                  "code": "ERR_NOT_FOUND"})
            return

        intent_name, param_map = TOOL_TO_INTENT[tool_name]

        # GET 类工具（不需要 body）直接 dispatch
        body = {}
        if method == "POST":
            cl = int(self.headers.get("Content-Length", 0))
            if cl > 0:
                try:
                    body = json.loads(self.rfile.read(cl).decode("utf-8"))
                except (ValueError, UnicodeDecodeError) as e:
                    self._send_json(400, {"ok": False,
                                          "err": f"invalid JSON: {e}",
                                          "code": "ERR_BAD_REQUEST"})
                    return
                except Exception as e:
                    self._send_json(400, {"ok": False,
                                          "err": f"failed to read body: {e}",
                                          "code": "ERR_BAD_REQUEST"})
                    return
            if not isinstance(body, dict):
                self._send_json(400, {"ok": False,
                                      "err": "body must be a JSON object",
                                      "code": "ERR_BAD_REQUEST"})
                return

        # 构造参数
        params = {}
        for body_key, intent_key in param_map.items():
            if body_key in body:
                params[intent_key] = body[body_key]

        # 调 dispatcher
        try:
            from executor.base import Intent, IntentType
            from executor.dispatcher import ExecutorDispatcher
            from executor.local import LocalExecutor
            if not hasattr(Handler, "_tool_dispatcher"):
                Handler._tool_dispatcher = ExecutorDispatcher(
                    pc_agent=None, dev_stub=None, local_executor=LocalExecutor(),
                )
            intent = Intent(IntentType[intent_name], params)
            result = Handler._tool_dispatcher.dispatch(intent)
            # 200 vs 400 看 ok
            code = 200 if result.get("ok") else 400
            self._send_json(code, result)
        except Exception as e:
            import traceback
            _log(f"[/api/v1/tools/{tool_name}] error: {e}\n{traceback.format_exc()}")
            self._send_json(500, {"ok": False,
                                  "err": f"internal error: {e}",
                                  "code": "ERR_INTERNAL"})

    @staticmethod
    def _save_state():
        try:
            with Handler._state_lock: data = dict(Handler._native_state)
            with open(Handler._state_file, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False)
        except Exception as e: _log(f"[Native] 状态持久化失败: {e}")

    @staticmethod
    def _load_state():
        try:
            if not os.path.exists(Handler._state_file): return False
            with open(Handler._state_file, "r", encoding="utf-8") as f: data = json.load(f)
            with Handler._state_lock:
                for k in ("colorTemp", "gamma", "volume"):
                    if k in data: Handler._native_state[k] = data[k]
            return True
        except Exception as e: _log(f"[Native] 状态恢复失败: {e}"); return False

    @staticmethod
    def _bootstrap_volume():
        # Plan 1: csc.exe / waveOutGetVolume removed. Linux impl comes in Plan 2 (linux/pulseaudio.py).
        if Handler._load_state():
            vol = Handler._native_state.get("volume", 50)
            _log(f"[Native] 音量启动: 从持久化文件恢复 volume={vol}%")
            return
        _log("[Native] 音量启动: 无持久化状态，使用默认 50% (Linux 启动桩)")

    def _send_json(self, code, payload):
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self._cors_headers()
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _send_error_json(self, code, msg):
        payload = json.dumps({"error": {"message": msg}}).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self._cors_headers()
        self.end_headers()
        self.wfile.write(payload)


def main():
    Handler._bootstrap_volume()

    # 解析命令行参数
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=LISTEN_PORT)
    parser.add_argument("--bind", default="127.0.0.1")
    args = parser.parse_args()

    server = ThreadedHTTPServer((args.bind, args.port), Handler)
    print("=" * 56)
    print(f"  Voice AI Proxy v3 (threaded)")
    print(f"  http://{args.bind}:{args.port}")
    print(f"  /ollama/* --> {_OLLAMA_CONFIG['host']}:{_OLLAMA_CONFIG['port']}")
    print(f"  /api/v1/tools/* (OpenClaw integration)")
    print("=" * 56)

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutdown.")
        server.shutdown()


if __name__ == "__main__":
    main()
