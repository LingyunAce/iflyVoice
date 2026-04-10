#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Ollama Local Proxy Server v3
- ThreadingHTTPServer (multi-threaded, no blocking)
- Raw socket streaming for chat/generate
- Static file serving
"""

import os
import sys
import json
import socket
import subprocess
from http.server import HTTPServer, BaseHTTPRequestHandler
from socketserver import ThreadingMixIn

OLLAMA_HOST = "127.0.0.1"
OLLAMA_PORT = 11434
LISTEN_PORT = 18766
STATIC_DIR = os.path.dirname(os.path.abspath(__file__)) or "."


class ThreadedHTTPServer(ThreadingMixIn, HTTPServer):
    """每个请求一个线程，互不阻塞"""
    allow_reuse_address = True
    daemon_threads = True


class Handler(BaseHTTPRequestHandler):
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
        if self.path.startswith("/ollama/"):
            self._proxy("GET")
        elif self.path.startswith("/i2c/"):
            self._handle_i2c()
        else:
            self._serve_static()

    def do_POST(self):
        if self.path.startswith("/ollama/"):
            self._proxy("POST")
        elif self.path.startswith("/i2c/"):
            self._handle_i2c()
        else:
            self.send_error(404)

    # ── CORS helper ──
    def _cors_headers(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Cache-Control", "no-cache")

    # ── Static file serving ──
    def _serve_static(self):
        path = self.path.split("?")[0].split("#")[0]
        if path == "/":
            path = "/index.html"
        filepath = os.path.normpath(os.path.join(STATIC_DIR, path.lstrip("/")))
        if not filepath.startswith(STATIC_DIR):
            self.send_error(403)
            return
        try:
            with open(filepath, "rb") as f:
                data = f.read()
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
        except FileNotFoundError:
            self.send_error(404)
        except Exception as e:
            self.send_error(500, str(e))

    # ── Ollama proxy via raw socket ──
    def _proxy(self, method):
        target_path = self.path.replace("/ollama/", "/", 1)

        # Read POST body
        body = None
        if method == "POST":
            cl = int(self.headers.get("Content-Length", 0))
            if cl > 0:
                try:
                    body = self.rfile.read(cl)
                except Exception as e:
                    self._send_error_json(400, f"Read error: {e}")
                    return

        is_streaming = "/chat" in target_path or "/generate" in target_path

        sock = None
        try:
            # Connect to Ollama with timeout
            sock = socket.create_connection((OLLAMA_HOST, OLLAMA_PORT), timeout=10)
            sock.settimeout(None)  # Remove timeout after connect

            # Build raw HTTP/1.0 request
            req_lines = [f"{method} {target_path} HTTP/1.0"]
            req_lines.append(f"Host: {OLLAMA_HOST}:{OLLAMA_PORT}")
            if body is not None:
                req_lines.append(f"Content-Type: application/json")
                req_lines.append(f"Content-Length: {len(body)}")
            req_lines.append("Connection: close")
            req_lines.append("")
            req_data = "\r\n".join(req_lines).encode() + (b"\r\n" if body is None else b"\r\n" + (body or b""))
            sock.sendall(req_data)

            # Parse response status line
            status_line = self._sock_readline(sock)
            if not status_line:
                raise Exception("Empty response from Ollama")
            parts = status_line.split(" ", 2)
            code = int(parts[1]) if len(parts) >= 2 else 502

            # Parse response headers
            resp_ct = "application/json"
            while True:
                hline = self._sock_readline(sock).strip()
                if not hline:
                    break
                if hline.lower().startswith("content-type:"):
                    resp_ct = hline.split(":", 1)[1].strip()

            # Send client headers
            self.send_response(code)
            self.send_header("Content-Type", resp_ct)
            self._cors_headers()
            self.end_headers()

            # Stream body to client
            while True:
                chunk = sock.recv(4096)
                if not chunk:
                    break
                try:
                    self.wfile.write(chunk)
                    self.wfile.flush()
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
                try:
                    sock.close()
                except Exception:
                    pass

    def _sock_readline(self, sock):
        """Read until \r\n from socket"""
        buf = b""
        while True:
            ch = sock.recv(1)
            if not ch:
                return buf.decode("utf-8", errors="replace")
            buf += ch
            if buf.endswith(b"\r\n"):
                return buf[:-2].decode("utf-8", errors="replace")

    # ── I2C / ADB 代理路由 ──
    def _handle_i2c(self):
        """处理 /i2c/* 路由：ADB + i2cset 命令执行"""
        path = self.path.split("?")[0]

        # GET: 检查 ADB 连接状态
        if path == "/i2c/adb/status" or path == "/i2c/status":
            self._check_adb_connection()
            return

        # POST: 执行 i2cset 命令
        if path == "/i2c/i2cset" or path == "/i2c/command":
            cl = int(self.headers.get("Content-Length", 0))
            if cl <= 0:
                return self._send_json(400, {"success": False, "error": "Missing request body"})
            try:
                body = json.loads(self.rfile.read(cl).decode("utf-8"))
            except Exception as e:
                return self._send_json(400, {"success": False, "error": f"Invalid JSON: {e}"})
            self._execute_i2c_command(body)
            return

        self._send_json(404, {"success": False, "error": f"Unknown I2C endpoint: {path}"})

    def _check_adb_connection(self):
        """检查 ADB 是否可用且设备已连接"""
        try:
            result = subprocess.run(
                ["adb", "devices"],
                capture_output=True, text=True, timeout=10
            )
            lines = result.stdout.strip().split("\n")
            devices = [l for l in lines[1:] if l.strip() and "device" in l]
            self._send_json(200, {
                "connected": len(devices) > 0,
                "deviceCount": len(devices),
                "devices": devices,
                "output": result.stdout,
            })
        except FileNotFoundError:
            self._send_json(200, {"connected": False, "error": "ADB not found in PATH"})
        except subprocess.TimeoutExpired:
            self._send_json(200, {"connected": False, "error": "ADB command timed out"})
        except Exception as e:
            self._send_json(200, {"connected": False, "error": str(e)})

    def _execute_i2c_command(self, body):
        """通过 adb shell 执行 i2cset 命令"""
        cmd_type = body.get("command", "i2cset")
        args = body.get("args", [])

        if cmd_type == "i2cset":
            adb_cmd = ["adb", "shell", "i2cset"] + args
        else:
            # 通用命令模式
            adb_cmd = ["adb", "shell"] + [cmd_type] + args

        try:
            sys.stderr.write(f"[I2C] Executing: {' '.join(adb_cmd)}\n")
            result = subprocess.run(
                adb_cmd,
                capture_output=True, text=True, timeout=30,
            )

            success = result.returncode == 0
            resp = {
                "success": success,
                "command": " ".join(adb_cmd),
                "returnCode": result.returncode,
                "stdout": (result.stdout or "").strip(),
                "stderr": (result.stderr or "").strip(),
            }
            status_code = 200 if success else 502
            self._send_json(status_code, resp)
        except FileNotFoundError:
            self._send_json(502, {"success": False, "error": "ADB executable not found in PATH"})
        except subprocess.TimeoutExpired:
            self._send_json(504, {"success": False, "error": "Command execution timed out (30s)"})
        except Exception as e:
            self._send_json(500, {"success": False, "error": str(e)})

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
    server = ThreadedHTTPServer(("127.0.0.1", LISTEN_PORT), Handler)
    print("=" * 56)
    print(f"  Voice AI Proxy v3 (threaded)")
    print(f"  http://localhost:{LISTEN_PORT}")
    print(f"  /ollama/* --> {OLLAMA_HOST}:{OLLAMA_PORT}")
    print("=" * 56)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutdown.")
        server.shutdown()


if __name__ == "__main__":
    main()
