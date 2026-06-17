#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Ollama Local Proxy Server v3 — with system tray support
"""
import os, sys, json, socket, subprocess, threading, struct
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
        if self.path.startswith("/config/"):
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
        path = self.path.split("?")[0].split("#")[0]
        endpoint = path.replace("/native/", "", 1).strip("/")
        if not endpoint: return self._send_json(404, {"success": False, "error": "No native endpoint"})
        body = {}
        if method == "POST":
            cl = int(self.headers.get("Content-Length", 0))
            if cl > 0:
                try: body = json.loads(self.rfile.read(cl).decode("utf-8"))
                except Exception: return self._send_json(400, {"success": False, "error": "Invalid JSON"})
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
        try: handler()
        except Exception as e:
            import traceback; _log(f"[Native] /{endpoint} error: {e}\n{traceback.format_exc()}\n")
            self._send_json(500, {"success": False, "error": str(e)})

    def _native_status(self):
        # Plan 1: WMI removed (Windows-only). Linux impl comes in Plan 2 (linux/backlight.py).
        with Handler._state_lock:
            state = dict(Handler._native_state)
        self._send_json(200, {"connected": False, "platform": sys.platform, "state": state,
                              "note": "WMI not available on Linux; see Plan 2"})

    def _native_set_brightness(self, body):
        # Plan 1: WMI removed (Windows-only). Linux impl comes in Plan 2 (linux/backlight.py).
        value = int(body.get("value", 50)); value = max(0, min(100, value))
        with Handler._state_lock:
            Handler._native_state["brightness"] = value
        Handler._save_state()
        self._send_json(200, {"success": False, "platform": sys.platform,
                              "error": "WMI not available on Linux; see Plan 2", "brightness": value})

    def _native_set_contrast(self, body):
        # Plan 1: WMI removed (Windows-only). Linux impl comes in Plan 2 (linux/backlight.py).
        value = int(body.get("value", 50)); value = max(0, min(100, value))
        self._send_json(200, {"success": False, "platform": sys.platform,
                              "error": "WMI not available on Linux; see Plan 2", "contrast": value})

    def _apply_gamma_ramp(self, gamma_val, r_gain=255, g_gain=255, b_gain=255):
        import ctypes
        from ctypes import windll, byref, c_uint16, Structure
        class GAMMARAMP(Structure):
            _fields_ = [("Red", c_uint16 * 256), ("Green", c_uint16 * 256), ("Blue", c_uint16 * 256)]
        gamma = GAMMARAMP()
        for i in range(256):
            x = i / 255.0
            r = min(255, int((x ** gamma_val) * r_gain))
            g = min(255, int((x ** gamma_val) * g_gain))
            b = min(255, int((x ** gamma_val) * b_gain))
            gamma.Red[i] = min(65535, r * 257); gamma.Green[i] = min(65535, g * 257); gamma.Blue[i] = min(65535, b * 257)
        user32 = windll.user32; gdi32 = windll.gdi32
        dm = user32.GetDesktopWindow(); dc = user32.GetDC(dm); result = 0
        if dc: result = gdi32.SetDeviceGammaRamp(dc, byref(gamma)); user32.ReleaseDC(dm, dc)
        if not result:
            dc2 = user32.GetDC(0)
            if dc2: result = gdi32.SetDeviceGammaRamp(dc2, byref(gamma)); user32.ReleaseDC(0, dc2)
        return result

    def _native_set_gamma(self, body):
        value = int(body.get("value", 50)); value = max(0, min(100, value))
        gamma_val = 2.5 - (value / 100.0 * 2.0)
        try:
            result = self._apply_gamma_ramp(gamma_val)
            if result:
                with Handler._state_lock: Handler._native_state["gamma"] = value
                Handler._save_state()
                self._send_json(200, {"success": True, "gamma": value, "gammaVal": round(gamma_val, 2)})
            else: self._send_json(200, {"success": False, "error": "SetDeviceGammaRamp failed"})
        except Exception as e:
            import traceback; _log(f"[Native] 伽马设置异常: {e}\n{traceback.format_exc()}\n")
            self._send_json(500, {"success": False, "error": str(e)})

    def _native_get_gamma(self):
        with Handler._state_lock: state = dict(Handler._native_state)
        self._send_json(200, {"gamma": state["gamma"], "colorTemp": state["colorTemp"]})

    def _native_power_off(self):
        try:
            import ctypes; from ctypes import windll
            user32 = windll.user32
            HW_BROADCAST = 0xFFFF; WM_SYSCOMMAND = 0x0112; SC_MONITORPOWER = 0xF170
            user32.SendMessageW(HW_BROADCAST, WM_SYSCOMMAND, SC_MONITORPOWER, 2)
            _log("[Native] 息屏完成")
            self._send_json(200, {"success": True, "action": "screen_off"})
        except Exception as e:
            import traceback; _log(f"[Native] 息屏异常: {e}\n{traceback.format_exc()}\n")
            self._send_json(500, {"success": False, "error": str(e)})

    @staticmethod
    def _run_nircmd(args, timeout=5):
        import os, subprocess as _sp, sys as _sys
        _nircmd_dir = _sys._MEIPASS if getattr(_sys, "frozen", False) else STATIC_DIR
        nircmd = os.path.join(_nircmd_dir, "nircmd.exe")
        if not os.path.exists(nircmd): return None
        si = _sp.STARTUPINFO()
        si.dwFlags |= _sp.STARTF_USESHOWWINDOW; si.wShowWindow = 0
        try:
            return _sp.run([nircmd] + args, capture_output=True, text=True, timeout=timeout, startupinfo=si)
        except Exception: return None

    def _native_set_volume(self, body):
        value = int(body.get("value", 50)); value = max(0, min(100, value))
        raw_val = int(round(value * 65535 / 100.0))
        result = self._run_nircmd(["setsysvolume", str(raw_val)])
        if result is None: self._send_json(500, {"success": False, "error": "nircmd.exe not found or failed"}); return
        if result.returncode == 0:
            with Handler._state_lock: Handler._native_state["volume"] = value
            Handler._save_state()
            self._send_json(200, {"success": True, "volume": value})
        else:
            err = result.stderr.strip() or result.stdout.strip()
            self._send_json(200, {"success": False, "error": err})

    def _native_get_volume(self):
        with Handler._state_lock: vol = Handler._native_state.get("volume", 50)
        _log(f"[Native] 音量读取: 返回缓存 {vol}%")
        self._send_json(200, {"volume": vol, "source": "cached"})

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
        if Handler._load_state():
            vol = Handler._native_state.get("volume", 50)
            _log(f"[Native] 音量启动: 从持久化文件恢复 volume={vol}%"); return
        vol_exe = os.path.join(STATIC_DIR, "_vol_read.exe")
        vol_src = os.path.join(STATIC_DIR, "_vol_test.cs")
        csc_path = None
        for candidate in [
            os.path.join(os.environ.get("windir", ""), r"Microsoft.NET\Framework64\v4.0.30319", "csc.exe"),
            os.path.join(os.environ.get("windir", ""), r"Microsoft.NET\Framework\v4.0.30319", "csc.exe"),
        ]:
            if os.path.isfile(candidate): csc_path = candidate; break
        if csc_path and os.path.exists(vol_src) and not os.path.exists(vol_exe):
            try:
                cwd = os.getcwd(); os.chdir(STATIC_DIR)
                compile_r = subprocess.run([csc_path, "/target:exe", f"/out:{os.path.basename(vol_exe)}", "/nologo", os.path.basename(vol_src)], capture_output=True, timeout=30,
                                            creationflags=subprocess.CREATE_NO_WINDOW)
                os.chdir(cwd)
                if compile_r.returncode == 0 and os.path.exists(vol_exe): _log("[Native] 音量启动: C# 编译成功")
                else: vol_exe = None
            except Exception as e: _log(f"[Native] 音量启动: C# 编译失败 {e}"); vol_exe = None
        elif not os.path.exists(vol_src): vol_exe = None
        if vol_exe and os.path.exists(vol_exe):
            try:
                run_r = subprocess.run([vol_exe], capture_output=True, text=True, timeout=10, errors="replace",
                                        creationflags=subprocess.CREATE_NO_WINDOW)
                out = run_r.stdout.strip()
                if out.lstrip('-').isdigit():
                    v = int(out)
                    if 0 <= v <= 100:
                        with Handler._state_lock: Handler._native_state["volume"] = v
                        Handler._save_state()
                        _log(f"[Native] 音量启动: C# 读取器 → {v}%"); return
            except Exception as e: _log(f"[Native] 音量启动: C# 读取器执行失败 {e}")
        try:
            import ctypes
            v = ctypes.c_uint32()
            ctypes.windll.winmm.waveOutGetVolume(0, ctypes.byref(v))
            lo = v.value & 0xFFFF; hi = (v.value >> 16) & 0xFFFF
            wave_pct = int((lo + hi) // 2 * 100 / 0xFFFF)
            if 0 <= wave_pct <= 100:
                with Handler._state_lock: Handler._native_state["volume"] = wave_pct
                Handler._save_state()
                _log(f"[Native] 音量启动: waveOut 近似值 → {wave_pct}% (仅参考)"); return
        except Exception as e: _log(f"[Native] 音量启动: waveOut 失败 ({e})")
        Handler._save_state()
        _log("[Native] 音量启动: 使用默认 50%")

    def _native_set_color_temp(self, body):
        value = int(body.get("value", 50)); value = max(0, min(100, value))
        try:
            import ctypes
            from ctypes import windll, byref, c_uint16, Structure
            class GAMMARAMP(Structure):
                _fields_ = [("Red", c_uint16 * 256), ("Green", c_uint16 * 256), ("Blue", c_uint16 * 256)]
            t = value / 100.0
            r_gain = 255 - int(t * 75); g_gain = 180 + int(t * 20); b_gain = 100 + int(t * 155)
            gamma_val_r = 1.0; gamma_val_g = 1.0; gamma_val_b = 1.0 + t * 0.25
            gamma = GAMMARAMP()
            for i in range(256):
                x = i / 255.0
                def rg(v, gv, g): return min(255, int((v ** gv) * g))
                r = rg(x, gamma_val_r, r_gain); g = rg(x, gamma_val_g, g_gain); b = rg(x, gamma_val_b, b_gain)
                gamma.Red[i] = min(65535, r * 257); gamma.Green[i] = min(65535, g * 257); gamma.Blue[i] = min(65535, b * 257)
            user32 = windll.user32; gdi32 = windll.gdi32
            dm = user32.GetDesktopWindow(); dc = user32.GetDC(dm); result = 0
            if dc: result = gdi32.SetDeviceGammaRamp(dc, byref(gamma)); user32.ReleaseDC(dm, dc)
            if not result:
                dc2 = user32.GetDC(0)
                if dc2: result = gdi32.SetDeviceGammaRamp(dc2, byref(gamma)); user32.ReleaseDC(0, dc2)
            if result:
                with Handler._state_lock: Handler._native_state["colorTemp"] = value
                Handler._save_state()
                self._send_json(200, {"success": True, "colorTemp": value})
            else:
                err = ctypes.get_last_error()
                self._send_json(200, {"success": False, "error": f"SetDeviceGammaRamp failed (err={err}). 尝试以管理员身份运行。"})
        except Exception as e:
            import traceback; _log(f"[Native] 色温设置异常: {e}\n{traceback.format_exc()}\n")
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
