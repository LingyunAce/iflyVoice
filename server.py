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
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
from socketserver import ThreadingMixIn

OLLAMA_HOST = "192.168.1.32"
OLLAMA_PORT = 11434
_OLLAMA_CONFIG = {"host": OLLAMA_HOST, "port": OLLAMA_PORT}  # 可动态修改
LISTEN_PORT = 18766
STATIC_DIR = os.path.dirname(os.path.abspath(__file__)) or "."

class ThreadedHTTPServer(ThreadingMixIn, HTTPServer):
    """每个请求一个线程，互不阻塞"""
    allow_reuse_address = True
    daemon_threads = True


class Handler(BaseHTTPRequestHandler):
    # 类级别状态：存储最后一次设置的色温/伽马/音量（读取时直接返回缓存值）
    # 用锁保护，避免多线程并发访问时互相覆盖
    _native_state = {"colorTemp": 50, "gamma": 50, "volume": 50}
    _state_lock = threading.Lock()
    _state_file = os.path.join(STATIC_DIR, ".native_state.json")  # 持久化路径
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
        if self.path.startswith("/exit"):
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(b'{"msg":"exiting"}')
            import sys
            sys.exit(0)
            return
        elif self.path.startswith("/config/"):
            self._handle_config("GET")
        elif self.path.startswith("/ollama/"):
            self._proxy("GET")
        elif self.path.startswith("/i2c/"):
            self._handle_i2c()
        elif self.path.startswith("/native/"):
            self._handle_native("GET")
        elif self.path.startswith("/ddcci/"):
            self._handle_ddcci("GET")
        else:
            self._serve_static()

    def do_POST(self):
        if self.path.startswith("/config/"):
            self._handle_config("POST")
        elif self.path.startswith("/ollama/"):
            self._proxy("POST")
        elif self.path.startswith("/i2c/"):
            self._handle_i2c()
        elif self.path.startswith("/sensevoice/"):
            self._handle_sensevoice()
        elif self.path.startswith("/native/"):
            self._handle_native("POST")
        elif self.path.startswith("/ddcci/"):
            self._handle_ddcci("POST")
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
            sock = socket.create_connection((_OLLAMA_CONFIG["host"], _OLLAMA_CONFIG["port"]), timeout=10)
            sock.settimeout(None)  # Remove timeout after connect

            # Build raw HTTP/1.0 request
            req_lines = [f"{method} {target_path} HTTP/1.0"]
            req_lines.append(f"Host: {_OLLAMA_CONFIG['host']}:{_OLLAMA_CONFIG['port']}")
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

        # ── DDC/CI 支持检测 ──
        if cmd_type == "ddc_check":
            self._check_ddc_ci_support()
            return

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

    def _check_ddc_ci_support(self):
        """检测 ADB 显示器是否支持 DDC/CI（通过尝试读取 VCP 0x00 字节）"""
        try:
            # 尝试用 i2cget 读取 DDC/CI VCP 0x00 (Manufacturer ID) 来判断是否支持
            test_cmd = ["adb", "shell", "i2cget", "-y", "-f", "0x37", "0x37", "0x00", "b"]
            sys.stderr.write(f"[DDC/CI] 检测中: {' '.join(test_cmd)}\n")
            result = subprocess.run(test_cmd, capture_output=True, text=True, timeout=10)

            if result.returncode == 0 and result.stdout.strip():
                self._send_json(200, {
                    "supported": True,
                    "detail": f"VCP readable: {result.stdout.strip()[:20]}",
                })
            else:
                # 尝试另一种方式：检查 i2cdetect 是否能看到显示器
                detect_cmd = ["adb", "shell", "i2cdetect", "-y", "-f", "0x37"]
                det_result = subprocess.run(detect_cmd, capture_output=True, text=True, timeout=10)
                output = (det_result.stdout or "").strip()
                # 如果能探测到 I2C 总线设备，说明基本通信正常
                has_devices = any(c in output for c in ['30', '31', '36', '37', '49', '50'])
                if has_devices:
                    self._send_json(200, {
                        "supported": True,
                        "detail": "I2C bus detected",
                    })
                else:
                    err = (result.stderr or det_result.stderr or "No response").strip()[:60]
                    self._send_json(200, {
                        "supported": False,
                        "reason": err,
                    })
        except FileNotFoundError:
            self._send_json(200, {"supported": False, "reason": "ADB not found"})
        except Exception as e:
            self._send_json(200, {"supported": False, "reason": str(e)[:80]})

    # ════════════════════════════════════════════
    #  DDC/CI (dxva2.dll) 外置显示器控制
    #  通过 Windows dxva2.dll 直接控制 HDMI 外接显示器的 VCP 特性
    #  物理显示器句柄: MonitorFromPoint(100,100) → PhysMon#1
    #  VCP: 0x10=亮度, 0x12=对比度 (范围 0-100)
    # ════════════════════════════════════════════
    def _handle_ddcci(self, method):
        """分发 /ddcci/* 路由"""
        path = self.path.split("?")[0].split("#")[0]
        endpoint = path.replace("/ddcci/", "", 1).strip("/")

        body = {}
        if method == "POST":
            cl = int(self.headers.get("Content-Length", 0))
            if cl > 0:
                try:
                    body = json.loads(self.rfile.read(cl).decode("utf-8"))
                except Exception:
                    return self._send_json(400, {"success": False, "error": "Invalid JSON"})

        handlers = {
            "status":         ("GET",  lambda: self._ddcci_status()),
            "brightness":     ("POST", lambda b=body: self._ddcci_set_vcp(b, 0x10, "brightness")),
            "contrast":       ("POST", lambda b=body: self._ddcci_set_vcp(b, 0x12, "contrast")),
            "contrast_read":  ("GET",  lambda: self._ddcci_get_vcp(0x12, "contrast")),
        }

        if endpoint not in handlers:
            return self._send_json(404, {"success": False, "error": f"Unknown DDC/CI endpoint: {endpoint}"})

        allowed, handler = handlers[endpoint]
        if allowed != "ALL" and method != allowed:
            return self._send_json(405, {"error": f"{method} not allowed for /ddcci/{endpoint}"})
        try:
            handler()
        except Exception as e:
            import traceback
            sys.stderr.write(f"[DDC/CI] /{endpoint} error: {e}\n{traceback.format_exc()}\n")
            self._send_json(500, {"success": False, "error": str(e)})

    def _handle_config(self, method):
        """处理 /config/* 动态配置路由"""
        path = self.path.split("?")[0]
        endpoint = path.replace("/config/", "", 1).strip("/")

        body = {}
        if method == "POST":
            content_len = int(self.headers.get("Content-Length", 0))
            if content_len > 0:
                body = json.loads(self.rfile.read(content_len))

        if endpoint == "ollama" and method == "POST":
            host = body.get("host", "")
            port = body.get("port", 11434)
            model = body.get("model", "qwen3-vl:4b")
            _OLLAMA_CONFIG["host"] = host
            _OLLAMA_CONFIG["port"] = int(port)
            sys.stderr.write(f"[Config] Ollama updated: {host}:{port} model={model}\n")
            self._send_json(200, {"success": True, "host": host, "port": port, "model": model})
        elif endpoint == "sensevoice" and method == "POST":
            url = body.get("base_url", "")
            Handler.SENSEVOICE_CONFIG["base_url"] = url
            sys.stderr.write(f"[Config] SenseVoice updated: {url}\n")
            self._send_json(200, {"success": True, "base_url": url})
        else:
            self._send_json(404, {"success": False, "error": f"Unknown config: {endpoint}"})

    @staticmethod
    def _get_physical_monitor():
        """获取外接显示器的物理句柄 (支持 DDC/CI)

        策略（多重容错，按优先级尝试）：
          1. MonitorFromPoint(100,100)      ← 已验证在 ps1 可用
          2. MonitorFromWindow(Desktop)     ← 获取桌面所在显示器  
          3. MonitorFromPoint(0,0)          ← 左上角（主显）
          4. EnumDisplayMonitors 回调       ← 兜底枚举全部

        拿到 HMON 后 → 取出所有物理监视器 → 逐个测 VCP 0x00 → 返回第一个响应的（外接屏）

        已验证场景（ddc_precise.ps1）：HMON=65537 下有2个物理设备
          PhysMon #1 Handle=0  → ✅ DDC/CI 正常（亮度40/对比50）← 外接屏
          PhysMon #2 Handle=1  → ❌ Error31 ← 内置屏

        Returns:
            (hPhysicalMonitor, err_msg) 二元组；失败时 hPhysicalMonitor 为 None
        """
        import ctypes
        from ctypes import windll, byref, c_ulong, c_uint, c_ubyte, c_char, c_wchar, Structure, c_long, POINTER, WINFUNCTYPE, pointer

        class PHYSICAL_MONITOR(Structure):
            _fields_ = [("handle", c_ulong), ("description", c_wchar * 128)]

        class POINT(Structure):
            _fields_ = [("x", c_long), ("y", c_long)]

        class RECT(Structure):
            _fields_ = [("left", c_long), ("top", c_long), ("right", c_long), ("bottom", c_long)]

        user32 = windll.user32
        dxva2 = windll.dxva2
        MON_DEFAULT_NEAREST = 0x00000002

        hmon = None
        src = ""

        # ── 方式1: MonitorFromPoint(100,100) + MON_DEFAULT_NEAREST ──
        pt = POINT(100, 100)
        hmon = user32.MonitorFromPoint(byref(pt), MON_DEFAULT_NEAREST)
        if hmon:
            src = "MonitorFromPoint(POINT(100,100), MON_DEFAULT_NEAREST)"
        else:
            # ── 方式2: MonitorFromWindow(GetDesktopWindow()) ──
            dw = user32.GetDesktopWindow()
            hmon = user32.MonitorFromWindow(dw, 0)
            if hmon:
                src = "MonitorFromWindow(Desktop)"
            else:
                # ── 方式3: MonitorFromPoint(0,0) ──
                pt0 = POINT(0, 0)
                hmon = user32.MonitorFromPoint(byref(pt0), MON_DEFAULT_NEAREST)
                if hmon:
                    src = "MonitorFromPoint(POINT(0,0), MON_DEFAULT_NEAREST)"
                else:
                    # ── 方式4: EnumDisplayMonitors 枚举第一个 ──
                    _found_hmons = []
                    _cb_type = WINFUNCTYPE(c_uint, c_ulong, c_ulong, POINTER(RECT), c_uint)

                    def _enum_cb(hm, hdc, lprect, lparam):
                        _found_hmons.append(int(hm))
                        return 1

                    _cb = _cb_type(_enum_cb)
                    user32.EnumDisplayMonitors(0, None, _cb, 0)
                    if _found_hmons:
                        hmon = _found_hmons[0]
                        src = "EnumDisplayMonitors[#0]"

        if not hmon:
            return None, "所有方式均无法获取 HMONITOR (point100/desktop/window/enum)"

        sys.stderr.write("[DDC/CI] HMON=%s (via %s)\n" % (hex(hmon), src))

        # ── 获取该 HMON 下所有物理监视器（注意：在 dxva2.dll，不是 user32）──
        num_phys = c_uint()
        if not dxva2.GetNumberOfPhysicalMonitorsFromHMONITOR(hmon, byref(num_phys)):
            return None, "GetNumberOfPhysicalMonitorsFromHMONITOR failed"
        if num_phys.value == 0:
            return None, "No physical monitors under HMON %s" % hex(hmon)

        phys_arr = (PHYSICAL_MONITOR * num_phys.value)()
        if not dxva2.GetPhysicalMonitorsFromHMONITOR(hmon, num_phys.value, byref(phys_arr)):
            return None, "GetPhysicalMonitorsFromHMONITOR failed"

        handles = [int(p.handle) for p in phys_arr]
        sys.stderr.write("[DDC/CI] 发现 %d 个物理监视器: %s\n" % (
            len(handles), ", ".join(hex(h) for h in handles)))

        # ── 逐个测试 VCP 0x00，找第一个 DDC/CI 响应的（外接屏）──
        # 策略：先试 VCP 0x00（制造商 ID），若无响应再试 VCP 0x10（亮度）
        # 返回第一个任意 VCP 代码有响应的物理监视器（外接显示器支持 DDC/CI）
        for idx, hPhys in enumerate(handles):
            vct = c_ubyte(); cur = c_uint(); mx = c_uint()
            try:
                ret = dxva2.GetVCPFeatureAndVCPFeatureReply(
                    hPhys, 0x00, byref(vct), byref(cur), byref(mx))
                if ret:
                    mid = "0x%04X" % cur.value
                    sys.stderr.write(
                        "[DDC/CI] OK PhysMon#%d Handle=%s MfgID=%s SELECTED\n"
                        % (idx, hex(hPhys), mid))
                    return hPhys, None
            except Exception as e:
                sys.stderr.write(
                    "[DDC/CI] X PhysMon#%d Handle=%s VCP0x00 err=%s\n"
                    % (idx, hex(hPhys), e))

        # VCP 0x00 全部无响应，备选：测 VCP 0x10（亮度），取第一个成功的
        for idx, hPhys in enumerate(handles):
            vct = c_ubyte(); cur = c_uint(); mx = c_uint()
            try:
                ret = dxva2.GetVCPFeatureAndVCPFeatureReply(
                    hPhys, 0x10, byref(vct), byref(cur), byref(mx))
                if ret:
                    sys.stderr.write(
                        "[DDC/CI] OK PhysMon#%d Handle=%s Brightness=%d (VCP 0x10 fallback) SELECTED\n"
                        % (idx, hex(hPhys), cur.value))
                    return hPhys, None
            except Exception as e:
                sys.stderr.write(
                    "[DDC/CI] X PhysMon#%d Handle=%s VCP0x10 err=%s\n"
                    % (idx, hex(hPhys), e))

        return None, "All %d phys-mon tested, none support DDC/CI" % len(handles)

    def _ddcci_status(self):
        """检测外置屏幕 DDC/CI 是否可用（读取 VCP 0x00 制造商 ID）"""
        hPhys, err = Handler._get_physical_monitor()
        if hPhys is None:
            return self._send_json(200, {
                "connected": False,
                "supported": False,
                "reason": err or "无法获取物理显示器句柄",
            })

        import ctypes
        from ctypes import windll, byref, c_ubyte, c_uint

        try:
            dxva2 = windll.dxva2
            vct = c_ubyte()
            cur_val = c_uint()
            max_val = c_uint()
            ret = dxva2.GetVCPFeatureAndVCPFeatureReply(
                hPhys, 0x00,          # VCP 0x00 = Manufacturer ID
                byref(vct),
                byref(cur_val),
                byref(max_val),
            )
            if ret:
                mid_hex = f"0x{cur_val.value:04X}"
                sys.stderr.write(f"[DDC/CI] ✓ ManufacturerID={mid_hex}\n")
                self._send_json(200, {
                    "connected": True,
                    "supported": True,
                    "manufacturerId": mid_hex,
                })
            else:
                # 备选：尝试读亮度 VCP 0x10
                ret2 = dxva2.GetVCPFeatureAndVCPFeatureReply(
                    hPhys, 0x10,
                    byref(c_ubyte()), byref(c_uint()), byref(c_uint()),
                )
                if ret2:
                    sys.stderr.write("[DDC/CI] ✓ VCP brightness readable\n")
                    self._send_json(200, {
                        "connected": True,
                        "supported": True,
                        "detail": "VCP brightness readable",
                    })
                else:
                    sys.stderr.write("[DDC/CI] ✗ DDC/CI no response\n")
                    self._send_json(200, {
                        "connected": True,
                        "supported": False,
                        "reason": "DDC/CI no response",
                    })
        except Exception as e:
            import traceback
            sys.stderr.write(f"[DDC/CI] 异常: {e}\n{traceback.format_exc()}\n")
            self._send_json(200, {
                "connected": False,
                "supported": False,
                "reason": str(e)[:120],
            })

    def _ddcci_set_vcp(self, body, vcp_code, control_name):
        """通过 DDC/CI SetVCPFeature 设置 VCP 值（0-100）"""
        value = int(body.get("value", 50))
        value = max(0, min(100, value))

        hPhys, err = Handler._get_physical_monitor()
        if hPhys is None:
            return self._send_json(200, {
                "success": False,
                "error": err or "无法获取物理显示器句柄",
            })

        import ctypes
        from ctypes import windll

        try:
            dxva2 = windll.dxva2
            ret = dxva2.SetVCPFeature(hPhys, vcp_code, value)
            if ret:
                sys.stderr.write(f"[DDC/CI] ✓ SetVCPFeature 0x{vcp_code:02X}({control_name})={value}%\n")
                self._send_json(200, {
                    "success": True,
                    control_name: value,
                    "vcpCode": f"0x{vcp_code:02X}",
                })
            else:
                sys.stderr.write(f"[DDC/CI] ✗ SetVCPFeature 0x{vcp_code:02X}({control_name})={value} failed\n")
                self._send_json(200, {
                    "success": False,
                    "error": f"SetVCPFeature 0x{vcp_code:02X} failed (monitor may not support this VCP code)",
                })
        except Exception as e:
            import traceback
            sys.stderr.write(f"[DDC/CI] SetVCPFeature 异常: {e}\n{traceback.format_exc()}\n")
            self._send_json(500, {"success": False, "error": str(e)})

    def _ddcci_get_vcp(self, vcp_code, control_name):
        """读取 VCP 值（0-100）"""
        hPhys, err = Handler._get_physical_monitor()
        if hPhys is None:
            return self._send_json(200, {"success": False, "error": err or "无法获取物理显示器句柄"})

        import ctypes
        from ctypes import windll, byref, c_ubyte, c_uint

        try:
            dxva2 = windll.dxva2
            vct = c_ubyte(); cur = c_uint(); mx = c_uint()
            ret = dxva2.GetVCPFeatureAndVCPFeatureReply(hPhys, vcp_code, byref(vct), byref(cur), byref(mx))
            if ret:
                self._send_json(200, {
                    "success": True,
                    control_name: int(cur.value),
                    "max": int(mx.value),
                    "vcpCode": f"0x{vcp_code:02X}",
                })
            else:
                self._send_json(200, {
                    "success": False,
                    "error": f"VCP 0x{vcp_code:02X} read failed",
                })
        except Exception as e:
            sys.stderr.write(f"[DDC/CI] GetVCP 0x{vcp_code:02X} 异常: {e}\n")
            self._send_json(500, {"success": False, "error": str(e)})

    # ── SenseVoice (xinference) 语音识别 ─────────────────────────
    # xinference SenseVoiceSmall HTTP API: POST /v1/audio/transcriptions
    SENSEVOICE_CONFIG = {
        "base_url": "http://192.168.1.32:9997",
        "api_key": "sk-86ccca26e58a8",
        "model": "SenseVoiceSmall",
    }

    def _handle_sensevoice(self):
        """Proxy: browser → server → xinference SenseVoiceSmall"""
        import urllib.request

        cfg = self.SENSEVOICE_CONFIG
        target_url = f"{cfg['base_url']}/v1/audio/transcriptions"

        # 读取浏览器发的 multipart body
        cl = int(self.headers.get("Content-Length", 0))
        if cl <= 0:
            return self._send_json(400, {"success": False, "error": "No audio data"})

        content_type = self.headers.get("Content-Type", "")
        original_body = self.rfile.read(cl)

        # 在原始 multipart body 前注入 model 字段
        # 格式: --boundary\r\nContent-Disposition: form-data; name="model"\r\n\r\nSenseVoiceSmall\r\n + 原始body
        boundary = ""
        for part in content_type.split(";"):
            part = part.strip()
            if part.lower().startswith("boundary="):
                boundary = part.split("=", 1)[1].strip().strip('"')
                break

        if not boundary:
            return self._send_json(400, {"success": False, "error": "No multipart boundary"})

        # 注入 model 字段到 multipart body 开头
        model_field = (
            f"--{boundary}\r\n"
            f"Content-Disposition: form-data; name=\"model\"\r\n"
            f"\r\n"
            f"{cfg['model']}\r\n"
        ).encode("utf-8")

        new_body = model_field + original_body
        new_content_type = content_type  # boundary 不变
        new_cl = len(new_body)

        try:
            req = urllib.request.Request(
                target_url,
                data=new_body,
                headers={
                    "Authorization": f"Bearer {cfg['api_key']}",
                    "Content-Type": new_content_type,
                    "Content-Length": str(new_cl),
                },
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=30) as resp:
                result = resp.read().decode("utf-8")
                data = json.loads(result)
                # xinference 返回 {"text": "识别结果"}
                text = data.get("text", "").strip()
                if text:
                    self._send_json(200, {"success": True, "text": text})
                else:
                    self._send_json(200, {"success": True, "text": "", "raw": data})
        except urllib.error.HTTPError as e:
            err_body = e.read().decode("utf-8", errors="replace")
            sys.stderr.write(f"[SenseVoice] HTTP {e.code}: {err_body}\n")
            self._send_json(502, {"success": False, "error": f"xinference {e.code}: {err_body[:200]}"})
        except Exception as e:
            sys.stderr.write(f"[SenseVoice] Error: {e}\n")
            self._send_json(500, {"success": False, "error": str(e)})

    # ── 内置屏幕（WMI/Gamma）路由分发 ─────────────────────────────
    def _handle_native(self, method):
        """分发 /native/<endpoint> 请求到对应的处理方法"""
        path = self.path.split("?")[0].split("#")[0]
        endpoint = path.replace("/native/", "", 1).strip("/")
        if not endpoint:
            return self._send_json(404, {"success": False, "error": "No native endpoint"})

        body = {}
        if method == "POST":
            cl = int(self.headers.get("Content-Length", 0))
            if cl > 0:
                try:
                    body = json.loads(self.rfile.read(cl).decode("utf-8"))
                except Exception:
                    return self._send_json(400, {"success": False, "error": "Invalid JSON"})

        # 路由表: endpoint → (allowed_method, handler)
        handlers = {
            "status":     ("GET",  lambda: self._native_status()),
            "brightness": ("POST", lambda b=body: self._native_set_brightness(b)),
            "contrast":   ("POST", lambda b=body: self._native_set_contrast(b)),
            "gamma":      ("ALL",  lambda b=body: self._native_set_gamma(b) if method == "POST" else self._native_get_gamma()),
            "color_temp": ("POST", lambda b=body: self._native_set_color_temp(b)),
            "volume":     ("ALL",  lambda b=body: self._native_set_volume(b) if method == "POST" else self._native_get_volume()),
            "power":      ("POST", lambda: self._native_power_off()),
        }

        if endpoint not in handlers:
            return self._send_json(404, {"success": False, "error": f"Unknown native endpoint: {endpoint}"})

        allowed_method, handler = handlers[endpoint]
        if allowed_method != "ALL" and method != allowed_method:
            return self._send_json(405, {"success": False, "error": f"{method} not allowed for /native/{endpoint}"})

        try:
            handler()
        except Exception as e:
            import traceback
            sys.stderr.write(f"[Native] /{endpoint} error: {e}\n{traceback.format_exc()}\n")
            self._send_json(500, {"success": False, "error": str(e)})

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
                with Handler._state_lock:
                    Handler._native_state["gamma"] = value
                Handler._save_state()
                self._send_json(200, {"success": True, "gamma": value, "gammaVal": round(gamma_val, 2)})
            else:
                self._send_json(200, {"success": False, "error": "SetDeviceGammaRamp failed"})
        except Exception as e:
            import traceback
            sys.stderr.write(f"[Native] 伽马设置异常: {e}\n{traceback.format_exc()}\n")
            self._send_json(500, {"success": False, "error": str(e)})

    def _native_get_gamma(self):
        """直接返回缓存的色温/伽马值（比从 GPU 估算更准确）"""
        with Handler._state_lock:
            state = dict(Handler._native_state)
        self._send_json(200, {
            "gamma": state["gamma"],
            "colorTemp": state["colorTemp"],
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

    @staticmethod
    def _run_nircmd(args, timeout=5):
        """调用 nircmd.exe 并隐藏控制台窗口（防止闪黑框）"""
        import os
        import subprocess as _sp
        nircmd = os.path.join(STATIC_DIR, "nircmd.exe")
        if not os.path.exists(nircmd):
            return None
        # 隐藏窗口: CREATE_NO_WINDOW (Windows) 或 STARTUPINFO + SW_HIDE
        si = _sp.STARTUPINFO()
        si.dwFlags |= _sp.STARTF_USESHOWWINDOW
        si.wShowWindow = 0  # SW_HIDE
        try:
            return _sp.run(
                [nircmd] + args,
                capture_output=True, text=True, timeout=timeout,
                startupinfo=si,
            )
        except Exception:
            return None

    def _native_set_volume(self, body):
        """通过 nircmd 设置系统主音量 (0-100)，隐藏窗口不弹窗"""
        value = int(body.get("value", 50))
        value = max(0, min(100, value))

        # nircmd setsysvolume 使用 0-65535 范围
        raw_val = int(round(value * 65535 / 100.0))

        result = self._run_nircmd(["setsysvolume", str(raw_val)])
        if result is None:
            self._send_json(500, {"success": False, "error": "nircmd.exe not found or failed"})
            return

        if result.returncode == 0:
            with Handler._state_lock:
                Handler._native_state["volume"] = value
            Handler._save_state()
            self._send_json(200, {"success": True, "volume": value})
        else:
            err = result.stderr.strip() or result.stdout.strip()
            self._send_json(200, {"success": False, "error": err})

    def _read_volume_from_registry(self):
        """从注册表读取近似系统音量值（备用方案）"""
        import winreg
        try:
            key = winreg.OpenKey(
                winreg.HKEY_LOCAL_MACHINE,
                r"SOFTWARE\Microsoft\Windows\CurrentVersion\Volume",
                0, winreg.KEY_READ
            )
            vol_str = None
            i = 0
            while True:
                try:
                    subkey_name = winreg.EnumKey(key, i)
                    subkey = winreg.OpenKey(key, subkey_name, 0, winreg.KEY_READ)
                    j = 0
                    while True:
                        try:
                            name, val, _ = winreg.EnumValue(subkey, j)
                            if "Volume" in name.lower():
                                vol_str = str(val)
                                break
                            j += 1
                        except OSError:
                            break
                    winreg.CloseKey(subkey)
                    if vol_str:
                        break
                    i += 1
                except OSError:
                    break
            winreg.CloseKey(key)

            if vol_str is not None:
                return int(vol_str) * 100 // 65535
        except Exception:
            pass
        return None

    def _native_get_volume(self):
        """返回当前系统主音量。
        由于本机 CoreAudio COM 注册表缺失(0x80040154)，nircmd getsysvolume 超时，
        无法直接读取真实系统主音量。返回值来源：
          - 上次通过助手 SET 的值（最准确）
          - 持久化文件恢复（跨会话）
          - 启动时校准的近似值
        如果用户在 Windows 托盘手动调了音量但未在助手中调节过，可能显示旧值。
        需要在助手中拖动一次滑块即可重新同步。"""
        with Handler._state_lock:
            vol = Handler._native_state.get("volume", 50)
        sys.stderr.write(f"[Native] 音量读取: 返回缓存 {vol}%\n")
        self._send_json(200, {"volume": vol, "source": "cached"})

    @staticmethod
    def _save_state():
        """将当前状态持久化到 JSON 文件"""
        try:
            with Handler._state_lock:
                data = dict(Handler._native_state)
            with open(Handler._state_file, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False)
        except Exception as e:
            sys.stderr.write(f"[Native] 状态持久化失败: {e}\n")

    @staticmethod
    def _load_state():
        """从 JSON 文件恢复状态（如果存在）"""
        try:
            if not os.path.exists(Handler._state_file):
                return False
            with open(Handler._state_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            with Handler._state_lock:
                for k in ("colorTemp", "gamma", "volume"):
                    if k in data:
                        Handler._native_state[k] = data[k]
            return True
        except Exception as e:
            sys.stderr.write(f"[Native] 状态恢复失败: {e}\n")
            return False

    @staticmethod
    def _bootstrap_volume():
        """Server 启动时初始化音量缓存。
        本机所有限制：
          - nircmd getsysvolume → 挂起超时
          - CoreAudio COM (MMDeviceEnumerator) → 注册表缺失 0x80040154
          - Mixer API → 无可用音频线路
          - waveOutGetVolume → 返回波形设备音量(非系统主音量)

        策略优先级（按准确度排序）：
          1. .native_state.json 持久化文件 ← 最可靠（上次 SET 写入的值）
          2. C# 编译的 exe 调 CoreAudio ← 如果某天注册表修复了可能工作
          3. waveOut 近似值 ← 仅作参考，通常不准
          4. 默认 50
        """
        # ── 策略1: 持久化文件 ──
        if Handler._load_state():
            vol = Handler._native_state.get("volume", 50)
            sys.stderr.write(f"[Native] 音量启动: 从持久化文件恢复 volume={vol}%\n")
            # 可选：用 nircmd setsysvolume 把缓存值写回系统，确保一致
            # （注意：这会覆盖用户在 Windows 托盘手动设置的值！所以默认不这样做）
            return

        # ── 策略2: 尝试编译并运行 C# CoreAudio 读取器 ──
        vol_exe = os.path.join(STATIC_DIR, "_vol_read.exe")
        vol_src = os.path.join(STATIC_DIR, "_vol_test.cs")
        csc_path = None
        for candidate in [
            os.path.join(os.environ.get("windir", ""), r"Microsoft.NET\Framework64\v4.0.30319", "csc.exe"),
            os.path.join(os.environ.get("windir", ""), r"Microsoft.NET\Framework\v4.0.30319", "csc.exe"),
        ]:
            if os.path.isfile(candidate):
                csc_path = candidate
                break

        if csc_path and os.path.exists(vol_src) and not os.path.exists(vol_exe):
            try:
                cwd = os.getcwd()
                os.chdir(STATIC_DIR)
                compile_r = subprocess.run(
                    [csc_path, "/target:exe", f"/out:{os.path.basename(vol_exe)}",
                     "/nologo", os.path.basename(vol_src)],
                    capture_output=True, timeout=30,
                )
                os.chdir(cwd)
                if compile_r.returncode == 0 and os.path.exists(vol_exe):
                    sys.stderr.write("[Native] 音量启动: C# 编译成功\n")
                else:
                    vol_exe = None
            except Exception as e:
                sys.stderr.write(f"[Native] 音量启动: C# 编译失败 {e}\n")
                vol_exe = None
        elif not os.path.exists(vol_src):
            vol_exe = None

        if vol_exe and os.path.exists(vol_exe):
            try:
                run_r = subprocess.run([vol_exe], capture_output=True, text=True, timeout=10,
                                       errors="replace")
                out = run_r.stdout.strip()
                if out.lstrip('-').isdigit():
                    v = int(out)
                    if 0 <= v <= 100:
                        with Handler._state_lock:
                            Handler._native_state["volume"] = v
                        Handler._save_state()
                        sys.stderr.write(f"[Native] 音量启动: C# 读取器 → {v}%\n")
                        return
            except Exception as e:
                sys.stderr.write(f"[Native] 音量启动: C# 读取器执行失败 {e}\n")

        # ── 策略3: waveOut 近似值（仅供参考）──
        try:
            import ctypes
            v = ctypes.c_uint32()
            ctypes.windll.winmm.waveOutGetVolume(0, ctypes.byref(v))
            lo = v.value & 0xFFFF
            hi = (v.value >> 16) & 0xFFFF
            wave_pct = int((lo + hi) // 2 * 100 / 0xFFFF)
            if 0 <= wave_pct <= 100:
                with Handler._state_lock:
                    Handler._native_state["volume"] = wave_pct
                Handler._save_state()
                sys.stderr.write(f"[Native] 音量启动: waveOut 近似值 → {wave_pct}% (仅参考)\n")
                return
        except Exception as e:
            sys.stderr.write(f"[Native] 音量启动: waveOut 失败 ({e})\n")

        # ── 最终 fallback ──
        Handler._save_state()
        sys.stderr.write("[Native] 音量启动: 使用默认 50%\n")

    @staticmethod
    def _ensure_volume_helper():
        """确保 C# 音量控制工具已编译，返回 exe 路径；失败返回 None"""
        import os

        src_path = os.path.join(STATIC_DIR, "_vol_helper.cs")
        exe_path = os.path.join(STATIC_DIR, "_vol_helper.exe")

        if os.path.exists(exe_path):
            return exe_path

        # 使用 dynamic 关键字做 COM 晚绑定，避免接口 vtable 定义问题
        csharp_code = r'''
using System;

class VolHelper {
    static void Main(string[] args) {
        if (args.Length < 1) return;
        try {
            // 通过 Type.GetTypeFromCLSID + Activator 创建 MMDeviceEnumerator
            var mmDevType = Type.GetTypeFromCLSID(
                new System.Guid("bcde0395-e52f-467c-8e3d-c57293534e89"));
            dynamic dev = Activator.CreateInstance(mmDevType);

            // GetDefaultAudioEndpoint(eRender=0, eConsole=1)
            dynamic speaker = dev.GetDefaultAudioEndpoint(0, 1);

            // AudioEndpointVolume 属性
            dynamic epVol = speaker.AudioEndpointVolume;

            if (args[0] == "set") {
                float val = float.Parse(args[1]) / 100.0f;
                epVol.MasterVolumeLevelScalar = val;
                Console.WriteLine("OK");
            } else if (args[0] == "get") {
                float scalar = epVol.MasterVolumeLevelScalar;
                Console.WriteLine((int)Math.Round(scalar * 100));
            }
        } catch (System.Runtime.InteropServices.COMException comEx) {
            Console.Error.WriteLine("COM_HR=0x" + comEx.ErrorCode.ToString("X8"));
            Environment.Exit(1);
        } catch (Exception ex) {
            Console.Error.WriteLine(ex.GetType().Name + ":" + ex.Message);
            Environment.Exit(1);
        }
    }
}
'''
        # 写源码文件
        with open(src_path, "w", encoding="utf-8") as f:
            f.write(csharp_code)

        # 查找 csc.exe
        csc = None
        for candidate in [
            os.path.join(os.environ.get("ProgramFiles(x86)", ""), "Microsoft.NET",
                         "Framework", "v4.0.30319", "csc.exe"),
            os.path.join(os.environ.get("windir", ""), "Microsoft.NET",
                         "Framework64", "v4.0.30319", "csc.exe"),
        ]:
            if os.path.isfile(candidate):
                csc = candidate
                break

        if not csc:
            sys.stderr.write("[Native] csc.exe not found\n")
            return None

        # 编译
        try:
            result = subprocess.run(
                [csc, "/target:exe", "/out:" + exe_path, "/nologo", src_path],
                capture_output=True, text=True, timeout=30,
            )
            if result.returncode == 0 and os.path.exists(exe_path):
                return exe_path
            else:
                sys.stderr.write(f"[Native] csc compile failed: {result.stderr}\n")
                return None
        except Exception as e:
            sys.stderr.write(f"[Native] csc compile error: {e}\n")
            return None

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
                with Handler._state_lock:
                    Handler._native_state["colorTemp"] = value
                Handler._save_state()
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
    # 启动时采样真实音量，解决首次 GET 返回默认值不准的问题
    Handler._bootstrap_volume()

    server = ThreadedHTTPServer(("127.0.0.1", LISTEN_PORT), Handler)
    print("=" * 56)
    print(f"  Voice AI Proxy v3 (threaded)")
    print(f"  http://localhost:{LISTEN_PORT}")
    print(f"  /ollama/* --> {_OLLAMA_CONFIG['host']}:{_OLLAMA_CONFIG['port']}")
    print("=" * 56)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutdown.")
        server.shutdown()


if __name__ == "__main__":
    main()
