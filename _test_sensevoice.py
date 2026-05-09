"""Test SenseVoice full chain through server.py proxy"""
import urllib.request, json, io, wave

# Create minimal silent WAV
buf = io.BytesIO()
w = wave.open(buf, 'w')
w.setnchannels(1); w.setsampwidth(2); w.setframerate(16000)
w.writeframes(b'\x00\x00' * 3200)  # 0.2s silence
w.close()
audio_data = buf.getvalue()
print(f"Test audio: {len(audio_data)} bytes")

boundary = '----TestBoundary12345'
fd = (
    f'--{boundary}\r\n'
    f'Content-Disposition: form-data; name="file"; filename="test.wav"\r\n'
    f'Content-Type: audio/wav\r\n\r\n'
).encode('utf-8')
footer = f'\r\n--{boundary}--\r\n'.encode('utf-8')
body = fd + audio_data + footer

print("\n=== [PROXY] /sensevoice/transcribe ===")
try:
    req = urllib.request.Request(
        'http://127.0.0.1:18766/sensevoice/transcribe',
        data=body,
        headers={'Content-Type': f'multipart/form-data; boundary={boundary}'}
    )
    resp = urllib.request.urlopen(req, timeout=30)
    result = resp.read().decode()
    print(f"Status: {resp.status}")
    print(f"Body: {result}")
except urllib.error.HTTPError as e:
    print(f"HTTP Error: {e.code}")
    print(f"Body: {e.read().decode()[:500]}")
except Exception as e:
    print(f"Error: {type(e).__name__}: {e}")
