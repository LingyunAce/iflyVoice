#!/usr/bin/env python3
"""Test DCR via raw I2C — bypass ddcutil verification."""
import subprocess

BUS = 11
ADDR = 0x37  # 7-bit DDC/CI address

# OSTAR DCR command: tag=OSTAR, cmd=0x0013, data=0 (off) or 1 (on)
# The full tag: 0x4F 0x53 0x54 0x41 0x52 0x00 0x13

# DDC/CI Write protocol:
# 0x51 = host source + length byte
# Then payload
# Then XOR checksum

# For writing to VCP 0xE6 with table data:
# Opcode 0x03 = VCP Set
# VCP code = 0xE6
# Value = (hi << 8) | lo

# Step 1: Try simple write — set VCP 0xE6 to 0x0013 (DCR off)
# i2ctransfer: w7@0x37 <hdr> <type> <op> <vcp> <val_hi> <val_lo> <chk>
hdr = 0x51
vcp_op = 0x03  # VCP Set
vcp_code = 0xE6
val_hi = 0x00
val_lo = 0x13  # DCR sub-cmd
chk = hdr ^ 0x84 ^ vcp_op ^ vcp_code ^ val_hi ^ val_lo

print(f"=== Write 0xE6 = 0x0013 (DCR=OFF) ===")
cmd = f"sudo i2ctransfer -y {BUS} w7@0x37 {hdr} 0x84 {vcp_op} {vcp_code} {val_hi} {val_lo} {chk}"
print(f"Command: {cmd}")
result = subprocess.run(cmd.split(), capture_output=True, text=True, timeout=5)
print(f"Result: rc={result.returncode}")

# Read back
print("\n=== Verify via ddcutil ===")
result = subprocess.run(["sudo", "ddcutil", "getvcp", "0xE6"], capture_output=True, text=True, timeout=5)
print(result.stdout.strip())

# Try DCR ON (val_lo=1)
print("\n=== Write 0xE6 = 0x0001 (DCR=ON) ===")
val_lo_on = 0x01
chk_on = hdr ^ 0x84 ^ vcp_op ^ vcp_code ^ val_hi ^ val_lo_on
cmd2 = f"sudo i2ctransfer -y {BUS} w7@0x37 {hdr} 0x84 {vcp_op} {vcp_code} {val_hi} {val_lo_on} {chk_on}"
result = subprocess.run(cmd2.split(), capture_output=True, text=True, timeout=5)
print(f"Result: rc={result.returncode}")

result = subprocess.run(["sudo", "ddcutil", "getvcp", "0xE6"], capture_output=True, text=True, timeout=5)
print(result.stdout.strip())
