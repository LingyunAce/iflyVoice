"""Test multipart parsing logic in isolation"""
# Simulate exactly what browser sends
boundary = "----WebKitFormBoundaryABC123"
audio = b"\x00" * 500  # dummy audio data

raw_body = (
    "--" + boundary + "\r\n"
    'Content-Disposition: form-data; name="file"; filename="recording.webm"\r\n'
    "Content-Type: audio/webm\r\n\r\n"
).encode() + audio + ("\r\n--" + boundary + "--\r\n").encode()

ct = f'multipart/form-data; boundary={boundary}'
print(f"Input: {len(raw_body)} bytes, CT: {ct}")

# Same logic as server.py _handle_sensevoice
orig_boundary = ""
for part in ct.split(";"):
    part = part.strip()
    if part.lower().startswith("boundary="):
        orig_boundary = part.split("=", 1)[1].strip('"')
        break

print(f"Parsed boundary: '{orig_boundary}'")

marker = ("--" + orig_boundary).encode()
end_marker = ("\r\n--" + orig_boundary).encode()

file_data = None
file_filename = "recording.webm"

idx = 0
while True:
    pos = raw_body.find(marker, idx)
    if pos < 0:
        print("Marker not found!")
        break
    after = raw_body[pos + len(marker):]
    if after.startswith(b"--"):
        print("Final boundary reached")
        break
    if not after.startswith(b"\r\n"):
        idx = pos + len(marker)
        continue

    h_end = after.find(b"\r\n\r\n", 2)
    if h_end < 0:
        idx = pos + len(marker)
        continue

    hdr = after[2:h_end].decode(errors="replace")
    c_start = h_end + 4
    n_bound = raw_body.find(end_marker, pos + len(marker))
    c_data = raw_body[c_start:n_bound if n_bound >= 0 else len(raw_body)]

    print(f"  Part headers: {hdr[:80]}")
    print(f"  Part data: {len(c_data)} bytes")

    if 'name="file"' in hdr or "name='file'" in hdr:
        file_data = c_data
        for ln in hdr.split("\r\n"):
            ln = ln.strip()
            if "filename=" in ln:
                file_filename = ln.split("=", 1)[1].strip('"')
                break
        print(f"  => FILE FOUND: {len(file_data)} bytes, name={file_filename}")
        break
    idx = pos + len(marker)

if file_data:
    print(f"\nSUCCESS: Extracted {len(file_data)} bytes ({file_filename})")
else:
    print("\nFAILED: No file data extracted")
