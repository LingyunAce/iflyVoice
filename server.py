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

# ── 火山引擎（豆包）云端模型配置 ──
VOLCENGINE_CONFIG = {
    "api_base": "https://ark.cn-beijing.volces.com/api/v3",  # 火山引擎 OpenAI 兼容端点
    "api_key": "dee5eff8-f907-442a-aad4-7caf1f684740",
    # coding-plan 对应的模型 endpoint ID（用户需要在火山引擎控制台确认）
    # 格式：ep-xxxxxxxxx 或直接用模型名
    "default_model": "doubao-1-5-pro-32k-250115",
}


class ThreadedHTTPServer(ThreadingMixIn, HTTPServer):
    """每个请求一个线程，互不阻塞"""
    allow_reuse_address = True
    daemon_threads = True


class Handler(BaseHTTPRequestHandler):
    # 类级别状态：存储最后一次设置的色温/伽马值（读取时直接返回，而非从GPU估算）
    _native_state = {"colorTemp": 50, "gamma": 50}
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
        elif self.path.startswith("/cloud/"):
            self._proxy_cloud("GET")
        elif self.path.startswith("/native/"):
            self._handle_native("GET")
        else:
            self._serve_static()

    def do_POST(self):
        if self.path.startswith("/ollama/"):
            self._proxy("POST")
        elif self.path.startswith("/i2c/"):
            self._handle_i2c()
        elif self.path.startswith("/cloud/"):
            self._proxy_cloud("POST")
        elif self.path.startswith("/native/"):
            self._handle_native("POST")
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

    # ── 火山引擎（云端模型）OpenAI 兼容代理 ──
    def _proxy_cloud(self, method):
        """将 /cloud/* 请求转发到火山引擎 OpenAI 兼容 API（支持 SSE 流式）"""
        target_path = self.path.replace("/cloud/", "/", 1)

        url = f"{VOLCENGINE_CONFIG['api_base']}{target_path}"

        # Read POST body
        body = None
        if method == "POST":
            cl = int(self.headers.get("Content-Length", 0))
            if cl > 0:
                try:
                    body = self.rfile.read(cl)
                except Exception as e:
                    self._send_json(400, {"error": {"message": f"Read error: {e}"}})
                    return

        try:
            import urllib.request
            import ssl

            req = urllib.request.Request(
                url,
                data=body,
                method=method,
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {VOLCENGINE_CONFIG['api_key']}",
                    # 禁用内容编码，让服务端保持 chunked / stream 原样返回
                    "Accept-Encoding": "identity",
                },
            )

            ctx = ssl.create_default_context()
            resp = urllib.request.urlopen(req, timeout=120, context=ctx)
            resp_status = resp.status
            content_type = resp.headers.get("Content-Type", "application/json")

            self.send_response(resp_status)
            self.send_header("Content-Type", content_type)
            self._cors_headers()
            # 流式响应不发送 Content-Length，改用 chunked transfer
            self.send_header("Transfer-Encoding", "chunked")
            self.end_headers()

            # 分块读取并实时转发（支持 SSE 流式）
            while True:
                chunk = resp.read(4096)
                if not chunk:
                    break
                try:
                    # HTTP/1.0 chunked encoding
                    chunk_hex = format(len(chunk), 'x')
                    self.wfile.write(chunk_hex.encode() + b"\r\n" + chunk + b"\r\n")
                    self.wfile.flush()
                except (BrokenPipeError, ConnectionResetError, OSError):
                    break

            # 发送 chunked 结束标记
            try:
                self.wfile.write(b"0\r\n\r\n")
                self.wfile.flush()
            except Exception:
                pass

            resp.close()

        except urllib.error.HTTPError as e:
            err_body = e.read().decode("utf-8", errors="replace")
            sys.stderr.write(f"[Cloud] 火山引擎 HTTP {e.code}: {err_body}\n")
            self._send_json(e.code, {
                "error": {"message": f"火山引擎 API 错误: {err_body}", "status": e.code}
            })
        except urllib.error.URLError as e:
            sys.stderr.write(f"[Cloud] 连接失败: {e.reason}\n")
            self._send_json(502, {"error": {"message": f"无法连接火山引擎: {e.reason}"}})
        except Exception as e:
            sys.stderr.write(f"[Cloud] 代理异常: {e}\n")
            self._send_json(500, {"error": {"message": f"代理错误: {e}"}})

    # ── Windows 本地屏幕（内置显示器）控制 ──
    def _handle_native(self, method):
        """处理 /native/* 路由：WMI 亮度 / DDC/CI 对比度"""
        path = self.path.split("?")[0]

        if path == "/native/status":
            self._native_status()
            return

        if path == "/native/brightness" and method == "GET":
            # 读取当前亮度（供回读确认用）
            ps = (
                "$c = Get-WmiObject -Namespace root\\WMI -Class WmiMonitorBrightness -ErrorAction SilentlyContinue | Select-Object -First 1; "
                "if ($c) { @{brightness=$c.CurrentBrightness} | ConvertTo-Json -Compress } "
                "else { @{brightness=$null} | ConvertTo-Json -Compress }"
            )
            out = subprocess.run(["powershell", "-NoProfile", "-Command", ps], capture_output=True, text=True)
            try:
                data = json.loads(out.stdout.strip())
                self._send_json(200, {"brightness": data.get("brightness")})
            except Exception:
                self._send_json(200, {"brightness": None})
            return

        if path == "/native/brightness" and method == "POST":
            cl = int(self.headers.get("Content-Length", 0))
            if cl <= 0:
                return self._send_json(400, {"success": False, "error": "Missing body"})
            try:
                body = json.loads(self.rfile.read(cl).decode("utf-8"))
            except Exception as e:
                return self._send_json(400, {"success": False, "error": f"Invalid JSON: {e}"})
            self._native_set_brightness(body)
            return

        if path == "/native/contrast" and method == "POST":
            cl = int(self.headers.get("Content-Length", 0))
            if cl <= 0:
                return self._send_json(400, {"success": False, "error": "Missing body"})
            try:
                body = json.loads(self.rfile.read(cl).decode("utf-8"))
            except Exception as e:
                return self._send_json(400, {"success": False, "error": f"Invalid JSON: {e}"})
            self._native_set_contrast(body)
            return

        if path == "/native/color_temp" and method == "POST":
            cl = int(self.headers.get("Content-Length", 0))
            if cl <= 0:
                return self._send_json(400, {"success": False, "error": "Missing body"})
            try:
                body = json.loads(self.rfile.read(cl).decode("utf-8"))
            except Exception as e:
                return self._send_json(400, {"success": False, "error": f"Invalid JSON: {e}"})
            self._native_set_color_temp(body)
            return

        if path == "/native/gamma" and method == "POST":
            cl = int(self.headers.get("Content-Length", 0))
            if cl <= 0:
                return self._send_json(400, {"success": False, "error": "Missing body"})
            try:
                body = json.loads(self.rfile.read(cl).decode("utf-8"))
            except Exception as e:
                return self._send_json(400, {"success": False, "error": f"Invalid JSON: {e}"})
            self._native_set_gamma(body)
            return

        # GET /native/gamma → 读取当前 gamma 曲线，估算 gamma 值和色温
        if path == "/native/gamma" and method == "GET":
            self._native_get_gamma()
            return

        if path == "/native/power" and method == "POST":
            self._native_power_off()
            return  # ← 关键：必须 return，否则会继续走到下面的 404

        self._send_json(404, {"success": False, "error": f"Unknown native endpoint: {path}"})

    def _native_status(self):
        """检测 Windows WMI 亮度接口是否可用"""
        script = (
            "$m = Get-WmiObject -Namespace root\\WMI -Class WmiMonitorBrightnessMethods -ErrorAction SilentlyContinue | Select-Object -First 1; "
            "if ($m) { "
            "  $c = Get-WmiObject -Namespace root\\WMI -Class WmiMonitorBrightness -ErrorAction SilentlyContinue | Select-Object -First 1; "
            "  @{connected=$true; brightness=($c.CurrentBrightness); instanceName=$m.InstanceName} | ConvertTo-Json -Compress"
            "} else {"
            "  @{connected=$false; error='WMI brightness not available'} | ConvertTo-Json -Compress"
            "}"
        )
        try:
            result = subprocess.run(
                ["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
                capture_output=True, text=True, timeout=15,
            )
            output = result.stdout.strip()
            if output:
                import json as _json
                data = _json.loads(output)
                self._send_json(200, data)
            else:
                self._send_json(200, {"connected": False, "error": "No WMI result"})
        except Exception as e:
            self._send_json(200, {"connected": False, "error": str(e)})

    def _native_set_brightness(self, body):
        """通过 WMI 设置亮度 (0-100)"""
        value = int(body.get("value", 50))
        value = max(0, min(100, value))

        script = (
            "$m = Get-WmiObject -Namespace root\\WMI -Class WmiMonitorBrightnessMethods -ErrorAction SilentlyContinue | Select-Object -First 1; "
            "if ($m) { $m.WmiSetBrightness(1, %d); Write-Host 'OK' } else { Write-Host 'ERR' }"
        ) % value

        try:
            result = subprocess.run(
                ["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
                capture_output=True, text=True, timeout=15,
            )
            out = result.stdout.strip()
            if "OK" in out:
                self._send_json(200, {"success": True, "brightness": value})
            else:
                self._send_json(200, {"success": False, "error": "WMI brightness not available"})
        except Exception as e:
            self._send_json(500, {"success": False, "error": str(e)})

    def _native_set_contrast(self, body):
        """通过 WMI WmiMonitorContrastMethods 设置对比度（部分设备支持）"""
        value = int(body.get("value", 50))
        value = max(0, min(100, value))

        script = (
            "$m = Get-WmiObject -Namespace root\\WMI -Class WmiMonitorContrastMethods -ErrorAction SilentlyContinue | Select-Object -First 1; "
            "if ($m) { "
            "try { $m.WmiSetContrast(%d, 1); Write-Host 'OK' } "
            "catch { Write-Host ('ERR:' + $_.Exception.Message) } "
            "} else { Write-Host 'ERR: WMI contrast not available' }"
        ) % value

        try:
            result = subprocess.run(
                ["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
                capture_output=True, text=True, timeout=15,
            )
            out = result.stdout.strip()
            if "OK" in out:
                self._send_json(200, {"success": True, "contrast": value})
            else:
                self._send_json(200, {"success": False, "error": out})
        except Exception as e:
            self._send_json(500, {"success": False, "error": str(e)})

    # ── 内部：构建并应用 gamma ramp ────────────────────────────────
    def _apply_gamma_ramp(self, gamma_val, r_gain=255, g_gain=255, b_gain=255):
        """构建 gamma ramp 并写入显卡，返回 True/False"""
        import ctypes
        from ctypes import windll, byref, c_uint16, Structure

        class GAMMARAMP(Structure):
            _fields_ = [
                ("Red",   c_uint16 * 256),
                ("Green", c_uint16 * 256),
                ("Blue",  c_uint16 * 256),
            ]

        gamma = GAMMARAMP()
        for i in range(256):
            x = i / 255.0
            r = min(255, int((x ** gamma_val) * r_gain))
            g = min(255, int((x ** gamma_val) * g_gain))
            b = min(255, int((x ** gamma_val) * b_gain))
            gamma.Red[i]   = min(65535, r * 257)
            gamma.Green[i] = min(65535, g * 257)
            gamma.Blue[i]  = min(65535, b * 257)

        user32 = windll.user32
        gdi32  = windll.gdi32
        dm = user32.GetDesktopWindow()
        dc = user32.GetDC(dm)
        result = 0
        if dc:
            result = gdi32.SetDeviceGammaRamp(dc, byref(gamma))
            user32.ReleaseDC(dm, dc)
        if not result:
            dc2 = user32.GetDC(0)
            if dc2:
                result = gdi32.SetDeviceGammaRamp(dc2, byref(gamma))
                user32.ReleaseDC(0, dc2)
        return result

    # ── 伽马调节（独立接口，不影响色温）─────────────────────────────
    def _native_set_gamma(self, body):
        """通过 SetDeviceGammaRamp 调节伽马曲线
        value 0-100: 0=gamma 2.5(暗), 50=gamma 1.0(标准), 100=gamma 0.5(亮)
        仅调节灰阶曲线，不改变颜色色温
        """
        value = int(body.get("value", 50))
        value = max(0, min(100, value))
        # 0→2.5, 50→1.0, 100→0.5
        gamma_val = 2.5 - (value / 100.0 * 2.0)

        try:
            result = self._apply_gamma_ramp(gamma_val)
            if result:
                Handler._native_state["gamma"] = value
                self._send_json(200, {"success": True, "gamma": value, "gammaVal": round(gamma_val, 2)})
            else:
                self._send_json(200, {"success": False, "error": "SetDeviceGammaRamp failed"})
        except Exception as e:
            import traceback
            sys.stderr.write(f"[Native] 伽马设置异常: {e}\n{traceback.format_exc()}\n")
            self._send_json(500, {"success": False, "error": str(e)})

    def _native_get_gamma(self):
        """直接返回缓存的色温/伽马值（比从 GPU 估算更准确）"""
        # 直接返回缓存值，不再从 GPU 估算（从 gamma ramp 反推色温/gamma 值误差大）
        self._send_json(200, {
            "gamma": Handler._native_state["gamma"],
            "colorTemp": Handler._native_state["colorTemp"],
        })

    def _native_power_off(self):
        """关闭内置显示器（息屏），模拟电源键行为。
        只发 SC_MONITORPOWER=2 消息，不锁屏，不防抖。
        与 curl 命令行为完全一致。
        """
        try:
            import ctypes
            from ctypes import windll
            user32 = windll.user32
            HW_BROADCAST = 0xFFFF
            WM_SYSCOMMAND = 0x0112
            SC_MONITORPOWER = 0xF170
            user32.SendMessageW(HW_BROADCAST, WM_SYSCOMMAND, SC_MONITORPOWER, 2)
            sys.stderr.write(f"[Native] 息屏完成\n")
            self._send_json(200, {"success": True, "action": "screen_off"})
        except Exception as e:
            import traceback
            sys.stderr.write(f"[Native] 息屏异常: {e}\n{traceback.format_exc()}\n")
            self._send_json(500, {"success": False, "error": str(e)})

    def _native_set_color_temp(self, body):
        """通过 SetDeviceGammaRamp 设置色温（软件模拟）
        value 0-100: 0=最暖(2700K偏黄), 100=最冷(6500K偏蓝)
        使用 RGB gamma ramp 曲线调整实现色温偏移
        """
        value = int(body.get("value", 50))
        value = max(0, min(100, value))

        try:
            import ctypes
            from ctypes import windll, byref, c_uint16, Structure
            import math

            class GAMMARAMP(Structure):
                _fields_ = [
                    ("Red",   c_uint16 * 256),
                    ("Green", c_uint16 * 256),
                    ("Blue",  c_uint16 * 256),
                ]

            t = value / 100.0

            # 色温映射：0=最暖(R强G中B弱)，100=最冷(R弱G中B强)
            r_gain = 255 - int(t * 75)   # 255→180
            g_gain = 180 + int(t * 20)   # 180→200
            b_gain = 100 + int(t * 155)  # 100→255

            # Gamma 值
            gamma_val_r = 1.0
            gamma_val_g = 1.0
            gamma_val_b = 1.0 + t * 0.25

            gamma = GAMMARAMP()
            for i in range(256):
                x = i / 255.0
                def rg(v, gv, g):
                    return min(255, int((v ** gv) * g))
                r = rg(x, gamma_val_r, r_gain)
                g = rg(x, gamma_val_g, g_gain)
                b = rg(x, gamma_val_b, b_gain)
                # Windows gamma ramp 用 0-65535 范围（16bit）
                gamma.Red[i]   = min(65535, r * 257)
                gamma.Green[i] = min(65535, g * 257)
                gamma.Blue[i]  = min(65535, b * 257)

            user32 = windll.user32
            gdi32  = windll.gdi32

            # 方式1：DC from GetDesktopWindow（可能被系统限权）
            dm = user32.GetDesktopWindow()
            dc = user32.GetDC(dm)
            result = 0
            if dc:
                result = gdi32.SetDeviceGammaRamp(dc, byref(gamma))
                user32.ReleaseDC(dm, dc)

            if not result:
                # 方式2：直接用 GetDC(0) 获取整个屏幕 DC
                dc2 = user32.GetDC(0)
                if dc2:
                    result = gdi32.SetDeviceGammaRamp(dc2, byref(gamma))
                    user32.ReleaseDC(0, dc2)

            if result:
                Handler._native_state["colorTemp"] = value
                self._send_json(200, {"success": True, "colorTemp": value})
            else:
                err = ctypes.get_last_error()
                self._send_json(200, {"success": False, "error": f"SetDeviceGammaRamp failed (err={err}). 尝试以管理员身份运行 server.py。"})
        except Exception as e:
            import traceback
            sys.stderr.write(f"[Native] 色温设置异常: {e}\n{traceback.format_exc()}\n")
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
