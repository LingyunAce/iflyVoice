"""Replace _handle_sensevoice in server.py (lines 295-360) with fixed version"""
filepath = r"C:\Users\a1318\WorkBuddy\xunfei_yuyin\iflyVoice\server.py"

with open(filepath, "r", encoding="utf-8") as f:
    lines = f.readlines()

print(f"Before: {len(lines)} lines")

# New method body (replacing lines 295 through 360 inclusive, 0-indexed)
new_lines = [
    '    def _handle_sensevoice(self):\n',
    '        """接收前端上传的音频文件，转发到 xinference SenseVoiceSmall 进行识别"""\n',
    '        try:\n',
    '            content_length = int(self.headers.get("Content-Length", 0))\n',
    '            if content_length <= 0:\n',
    '                return self._send_json(400, {"success": False, "error": "Missing audio data"})\n',
    '\n',
    '            raw_body = self.rfile.read(content_length)\n',
    '            ct = self.headers.get("Content-Type", "")\n',
    '\n',
    '            # 从 Content-Type 提取 boundary\n',
    '            orig_boundary = ""\n',
    '            for part in ct.split(";"):\n',
    '                part = part.strip()\n',
    '                if part.lower().startswith("boundary="):\n',
    '                    orig_boundary = part.split("=", 1)[1].strip(\'"\')\n',
    '                    break\n',
    '\n',
    '            if not orig_boundary:\n',
    '                return self._send_json(400, {"success": False, "error": "Missing boundary"})\n',
    '\n',
    '            # 手动解析 multipart：提取 file 字段的二进制数据\n',
    '            marker = ("--" + orig_boundary).encode()\n',
    '            end_marker = ("\\r\\n--" + orig_boundary).encode()\n',
    '\n',
    '            file_data = None\n',
    '            file_filename = "recording.webm"\n',
    '\n',
    '            idx = 0\n',
    '            while True:\n',
    '                pos = raw_body.find(marker, idx)\n',
    '                if pos < 0: break\n',
    '                after = raw_body[pos + len(marker):]\n',
    '                if after.startswith(b"--"): break\n',
    '                if not after.startswith(b"\\r\\n"): idx = pos + len(marker); continue\n',
    '\n',
    '                h_end = after.find(b"\\r\\n\\r\\n", 2)\n',
    '                if h_end < 0: idx = pos + len(marker); continue\n',
    '\n',
    '                hdr = after[2:h_end].decode(errors="replace")\n',
    '                c_start = h_end + 4\n',
    '                n_bound = raw_body.find(end_marker, pos + len(marker))\n',
    '                c_data = raw_body[c_start:n_bound if n_bound >= 0 else len(raw_body)]\n',
    '\n',
    '                if \'name="file"\' in hdr or "name=\'file\'" in hdr:\n',
    '                    file_data = c_data\n',
    '                    for ln in hdr.split("\\r\\n"):\n',
    '                        ln = ln.strip()\n',
    '                        if "filename=" in ln:\n',
    '                            file_filename = ln.split("=", 1)[1].strip(\'"\')\n',
    '                            break\n',
    '                    sys.stderr.write(f"[SenseVoice] 收到音频: {len(file_data)} bytes ({file_filename})\\n")\n',
    '                    break\n',
    '                idx = pos + len(marker)\n',
    '\n',
    '            if not file_data:\n',
    '                return self._send_json(400, {"success": False, "error": "No file field found"})\n',
    '\n',
    '            # 构建新 multipart：model 表单字段 + 文件数据\n',
    '            new_bnd = "----SVBnd" + __import__("os").urandom(4).hex()\n',
    '            parts = [\n',
    '                f"--{new_bnd}\\r\\n".encode(),\n',
    "                b'Content-Disposition: form-data; name=\"model\"\\r\\n\\r\\n',\n",
    '                self.SENSEVOICE_CONFIG["model"].encode(), b"\\r\\n",\n',
    '                f"--{new_bnd}\\r\\n".encode(),\n',
    '                (\'Content-Disposition: form-data; name="file"; filename="\' + file_filename + \'"\\r\\n\').encode(),\n',
    "                b'Content-Type: application/octet-stream\\r\\n\\r\\n',\n",
    '                file_data, b"\\r\\n",\n',
    '                f"--{new_bnd}--\\r\\n".encode(),\n',
    '            ]\n',
    '            new_body = b"".join(parts)\n',
    '\n',
    '            url = f"{self.SENSEVOICE_CONFIG[\'base_url\']}/v1/audio/transcriptions"\n',
    '            req = urllib.request.Request(url, data=new_body, method="POST", headers={\n',
    '                "Authorization": f"Bearer {self.SENSEVOICE_CONFIG[\'api_key\']}",\n',
    '                "Content-Type": f"multipart/form-data; boundary={new_bnd}",\n',
    '            })\n',
]

lines = lines[:295] + new_lines + lines[361:]

with open(filepath, "w", encoding="utf-8") as f:
    f.writelines(lines)

print(f"After: {len(lines)} lines")
print("DONE - verify with: python -c \"import py_compile; py_compile.compile(r'%s', doraise=True)\"" % filepath)
