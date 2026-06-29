#!/usr/bin/env python3
"""Test OSTAR DCR via I2C with full OSTAR tag in packet."""
import subprocess

BUS = 11
ADDR = "0x37"

hdr = 0x51
w_op = 0x03  # Write
r_op = 0x01  # Read
vcp = 0xE6
tag = [0x4F, 0x53, 0x54, 0x41, 0x52]  # OSTAR
hi_cmd = 0x00
lo_cmd = 0x13  # DCR

# Payload: W + VCP + 5 tag bytes + 2 cmd bytes + 2 data bytes = 11 bytes
# Type/length = 0x80 | 11 = 0x8B (11 bytes after type, including CHK)
typ = 0x80 | 0x0B

def send_packet(data_hi, data_lo, label):
    payload = [w_op, vcp] + tag + [hi_cmd, lo_cmd, data_hi, data_lo]
    chk = hdr ^ typ
    for b in payload:
        chk ^= b
    i2c_bytes = [str(hdr), str(typ)] + [str(b) for b in payload] + [str(chk)]
    i2c = f"sudo i2ctransfer -y {BUS} w12@{ADDR} " + " ".join(i2c_bytes)
    hex_str = " ".join(f"0x{x:02X}" for x in [hdr, typ] + payload + [chk])
    print(f"{label}: chk=0x{chk:02X}")
    print(f"  {hex_str}")
    r = subprocess.run(i2c.split(), capture_output=True, text=True, timeout=5)
    print(f"  rc={r.returncode}" + (f" err={r.stderr.strip()[:60]}" if r.stderr else ""))
    return r.returncode == 0

# DCR ON
send_packet(0x00, 0x01, "DCR ON ")
# DCR OFF
send_packet(0x00, 0x00, "DCR OFF")

# Also try with OstAR tag instead (caps)
tag2 = [0x4F, 0x73, 0x74, 0x41, 0x52]  # OstAR (mixed case?)
print("\nTrying different tag formats...")
for t, name in [([0x4F, 0x53, 0x54, 0x41, 0x52], "OSTAR"),
                 ([0x4F, 0x73, 0x74, 0x41, 0x52], "OstAR")]:
    payload = [w_op, vcp] + t + [hi_cmd, lo_cmd, 0x00, 0x01]
    chk = hdr ^ typ
    for b in payload:
        chk ^= b
    i2c_bytes = [str(hdr), str(typ)] + [str(b) for b in payload] + [str(chk)]
    i2c = f"sudo i2ctransfer -y {BUS} w12@{ADDR} " + " ".join(i2c_bytes)
    r = subprocess.run(i2c.split(), capture_output=True, text=True, timeout=5)
    print(f"Tag={name}: rc={r.returncode}")
