"""Replace _handle_sensevoice with minimal version - just prepend model field to body"""
filepath = r"C:\Users\a1318\WorkBuddy\xunfei_yuyin\iflyVoice\server.py"

with open(filepath, "r", encoding="utf-8") as f:
    lines = f.readlines()

# Find method boundaries
start = None
end = None
for i, l in enumerate(lines):
    if "def _handle_sensevoice(self):" in l and start is None:
        start = i

# Find next top-level def after start
for i in range(start + 1, len(lines)):
    stripped = lines[i].strip()
    if stripped.startswith("def ") and "handle" not in stripped:
        end = i
        break

if start is None or end is None:
    print(f"ERROR: start={start} end={end}")
    exit(1)

print(f"Replacing lines {start+1} to {end} (keeping {end-start-1} old lines)")

new_method_lines = [
    '    def _handle_sensevoice(self):\n',
    '        sys.stderr.write("[SV] START\\n")\n',
    '        try:\n',
    '            content_length = int(self.headers.get("Content-Length", 0))\n',
    '            if content_length <= 0:\n',
    '                return self._send_json(400, {"success": False, "error": "Missing audio data"})\n',
    '\n',
    '            raw_body = self.rfile.read(content_length)\n',
    '            ct = self.headers.get("Content-Type", "")\n',
    '            sys.stderr.write(f"[SV] body={len(raw_body)} ct={ct[:80]}\\n")\n',
    '\n',
    '            # Extract boundary from Content-Type\n',
    '            orig_boundary = ""\n',
    '            for part in ct.split(";"):\n',
    '                part = part.strip()\n',
    '                if part.lower().startswith("boundary="):\n',
    '                    orig_boundary = part.split("=", 1)[1].strip(\'"\')\n',
    '                    break\n',
    '\n',
    '            # Minimal fix: prepend model field to original multipart body\n',
    '            model_bytes = (\n',
    '                "--" + orig_boundary + "\\r\\n"\n',
    "                'Content-Disposition: form-data; name=\"model\"\\r\\n\\r\\n'\n",
    '                + self.SENSEVOICE_CONFIG["model"] + "\\r\\n"\n',
    '            ).encode()\n',
    '            new_body = model_bytes + raw_body\n',
    '\n',
    '            url = self.SENSEVOICE_CONFIG["base_url"] + "/v1/audio/transcriptions"\n',
    '            req = urllib.request.Request(url, data=new_body, method="POST", headers={\n',
    '                "Authorization": "Bearer " + self.SENSEVOICE_CONFIG["api_key"],\n',
    '                "Content-Type": ct,\n',
    '            })\n',
]

lines = lines[:start] + new_method_lines + lines[end:]

with open(filepath, "w", encoding="utf-8") as f:
    f.writelines(lines)

print(f"Done: {len(lines)} total lines")
