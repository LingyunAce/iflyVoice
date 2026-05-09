"""Test email multipart parsing for SenseVoice"""
import email.policy

boundary = "----TestBoundary12345"
audio_data = b"\x00\x00" * 100
body = (
    f'--{boundary}\r\n'
    'Content-Disposition: form-data; name="file"; filename="test.webm"\r\n'
    "Content-Type: audio/webm\r\n\r\n"
).encode() + audio_data + f'\r\n--{boundary}--\r\n'.encode()

ct = f"multipart/form-data; boundary={boundary}"
print(f"Body size: {len(body)} bytes")
print(f"CT: {ct}")

try:
    msg = email.message_from_bytes(
        b"Content-Type: " + ct.encode() + b"\r\nMIME-Version: 1.0\r\n" + body,
        policy=email.policy.default,
    )
    parts = list(msg.iter_parts())
    print(f"Message parts: {len(parts)}")
    found = False
    for part in msg.iter_attachments():
        data = part.get_payload(decode=True)
        cd = part.get("Content-Disposition", "")
        print(f"  Attachment: {len(data)} bytes, disp={cd}")
        # Extract filename
        filename = "unknown"
        for item in cd.split(";"):
            item = item.strip()
            if "filename=" in item:
                filename = item.split("=", 1)[1].strip('"')
                break
        print(f"  Filename: {filename}")
        found = True
    if not found:
        print("  No attachments found!")
except Exception as e:
    import traceback
    print(f"Error: {type(e).__name__}: {e}")
    traceback.print_exc()
