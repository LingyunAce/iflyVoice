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
        else:
            self._serve_static()

    def do_POST(self):
        if self.path.startswith("/ollama/"):
            self._proxy("POST")
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
