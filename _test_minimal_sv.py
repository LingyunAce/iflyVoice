"""Test if basic POST + body reading works"""
import urllib.request

boundary = "----Test123"
file_data = b"\x00" * 200
body = (
    "--" + boundary + "\r\n"
    'Content-Disposition: form-data; name="file"; filename="t.webm"\r\n'
    "Content-Type: audio/webm\r\n\r\n"
).encode() + file_data + ("\r\n--" + boundary + "--\r\n").encode()

print(f"Sending {len(body)} bytes...")

# Test 1: Basic echo endpoint (if exists)
try:
    req = urllib.request.Request(
        "http://127.0.0.1:18766/sensevoice/transcribe",
        data=body,
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
    )
    resp = urllib.request.urlopen(req, timeout=10)
    print(f"Status: {resp.status}")
    print(f"Body: {resp.read().decode()[:300]}")
except Exception as e:
    print(f"Error: {type(e).__name__}: {e}")

# Test 2: Simple POST to root (just to see if POST works at all)
print("\n--- Test POST / ---")
try:
    req2 = urllib.request.Request(
        "http://127.0.0.1:18766/",
        data=b"hello=world",
        method="POST",
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    resp2 = urllib.request.urlopen(req2, timeout=5)
    print(f"Status: {resp2.status}")
except Exception as e2:
    print(f"POST / Error: {type(e2).__name__}: {e2}")
