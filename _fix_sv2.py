"""Minimal _handle_sensevoice - debug version"""
filepath = r"C:\Users\a1318\WorkBuddy\xunfei_yuyin\iflyVoice\server.py"

with open(filepath, "r", encoding="utf-8") as f:
    content = f.read()

old = '''    def _handle_sensevoice(self):
        """接收前端上传的音频文件，转发到 xinference SenseVoiceSmall 进行识别"""
        try:
            content_length = int(self.headers.get("Content-Length", 0))
            if content_length <= 0:
                return self._send_json(400, {"success": False, "error": "Missing audio data"})

            raw_body = self.rfile.read(content_length)
            ct = self.headers.get("Content-Type", "")

            # 从 Content-Type 提取 boundary
            orig_boundary = ""
            for part in ct.split(";"):
                part = part.strip()
                if part.lower().startswith("boundary="):
                    orig_boundary = part.split("=", 1).strip('"')
                    break

            if not orig_boundary:
                return self._send_json(400, {"success": False, "error": "Missing boundary"})

            # 手动解析 multipart：提取 file 字段的二进制数据
            marker = ("--" + orig_boundary).encode()
            end_marker = ("\\r\\n--" + orig_boundary).encode()

            file_data = None
            file_filename = "recording.webm"

            idx = 0
            while True:
                pos = raw_body.find(marker, idx)
                if pos < 0: break
                after = raw_body[pos + len(marker):]
                if after.startswith(b"--"): break
                if not after.startswith(b"\\r\\n"): idx = pos + len(marker); continue

                h_end = after.find(b"\\r\\n\\r\\n", 2)
                if h_end < 0: idx = pos + len(marker); continue

                hdr = after[2:h_end].decode(errors="replace")
                c_start = h_end + 4
                n_bound = raw_body.find(end_marker, pos + len(marker))
                c_data = raw_body[c_start:n_bound if n_bound >= 0 else len(raw_body)]

                if 'name="file"' in hdr or "name='file'" in hdr:
                    file_data = c_data
                    for ln in hdr.split("\\r\\n"):
                        ln = ln.strip()
                        if "filename=" in ln:
                            file_filename = ln.split("=", 1).strip('"')
                            break
                    sys.stderr.write(f"[SenseVoice] 收到音频: {len(file_data)} bytes ({file_filename})\\n")
                    break
                idx = pos + len(marker)

            if not file_data:
                return self._send_json(400, {"success": False, "error": "No file field found"})

            # 构建新 multipart：model 表单字段 + 文件数据
            new_bnd = "----SVBnd" + __import__("os").urandom(4).hex()
            parts = [
                f"--{new_bnd}\\r\\n".encode(),
                b'Content-Disposition: form-data; name="model"\\r\\n\\r\\n',
                self.SENSEVOICE_CONFIG["model"].encode(), b"\\r\\n",
                f"--{new_bnd}\\r\\n".encode(),
                ('Content-Disposition: form-data; name="file"; filename="' + file_filename + '"\\r\\n').encode(),
                b'Content-Type: application/octet-stream\\r\\n\\r\\n',
                file_data, b"\\r\\n",
                f"--{new_bnd}--\\r\\n".encode(),
            ]
            new_body = b"".join(parts)'''

new = '''    def _handle_sensevoice(self):
        """接收前端上传的音频文件，转发到 xinference SenseVoiceSmall 进行识别"""
        import os as _os
        try:
            sys.stderr.write("[SV] START\\n")
            content_length = int(self.headers.get("Content-Length", 0))
            if content_length <= 0:
                return self._send_json(400, {"success": False, "error": "Missing audio data"})
            sys.stderr.write(f"[SV] content_length={content_length}\\n")

            raw_body = self.rfile.read(content_length)
            ct = self.headers.get("Content-Type", "")
            sys.stderr.write(f"[SV] raw_body={len(raw_body)} ct={ct[:80]}\\n")

            # 提取 boundary
            orig_boundary = ""
            for part in ct.split(";"):
                part = part.strip()
                if part.lower().startswith("boundary="):
                    orig_boundary = part.split("=", 1)[1].strip('"')
                    break
            sys.stderr.write(f"[SV] boundary='{orig_boundary}'\\n")

            # 简单方案：在原 body 前面插入 model 字段，复用原 boundary
            model_field = (
                "--" + orig_boundary + "\\r\\n"
                'Content-Disposition: form-data; name="model"\\r\\n\\r\\n'
                + self.SENSEVOICE_CONFIG["model"] + "\\r\\n"
            ).encode()
            new_body = model_field + raw_body

            url = self.SENSEVOICE_CONFIG["base_url"] + "/v1/audio/transcriptions"
            req = urllib.request.Request(url, data=new_body, method="POST", headers={
                "Authorization": "Bearer " + self.SENSEVOICE_CONFIG["api_key"],
                "Content-Type": ct,
            })
            sys.stderr.write(f"[V] forwarding to xinference...\\n")'''

if old in content:
    content = content.replace(old, new)
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(content)
    print("REPLACED OK")
else:
    print("NOT FOUND - trying partial match...")
    if "def _handle_sensevoice(self):" in content:
        count = content.count("def _handle_sensevoice(self):")
        print(f"Found {count} occurrences of _handle_sensevoice")
    else:
        print("Method not found at all!")
