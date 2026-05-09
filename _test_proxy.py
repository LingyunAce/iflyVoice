"""Quick proxy test for /sensevoice/transcribe"""
import urllib.request

boundary = "----Test123"
file_data = b"\x00\x00" * 200
body = (
    "--" + boundary + "\r\n"
    'Content-Disposition: form-data; name="file"; filename="t.webm"\r\n'
    "Content-Type: audio/webm\r\n\r\n"
).encode() + file_data + ("\r\n--" + boundary + "--\r\n").encode()

print(f"Sending {len(body)} bytes to proxy...")
try:
    req = urllib.request.Request(
        "http://127.0.0.1:18766/sensevoice/transcribe",
        data=body,
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
    )
    resp = urllib.request.urlopen(req, timeout=30)
    print(f"Status: {resp.status}")
    print(f"Body: {resp.read().decode()}")
except urllib.error.HTTPError as e:
    print(f"HTTP Error: {e.code}")
    print(f"Body: {e.read().decode()}")
except Exception as e:
    print(f"Error: {type(e).__name__}: {e}")
