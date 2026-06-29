#!/usr/bin/env python3
"""Test OSTAR DCR (Dynamic Contrast Ratio) via VCP 0xE6 sub-command 0x0013."""
import subprocess, struct

# OSTAR protocol packet:
# VCP 0xE6, tag=OSTAR(0x4F,0x53,0x54,0x41,0x52), cmd=0x0013, data=0 or 1

# Read current 0xE6 state
print("=== Current 0xE6 ===")
result = subprocess.run(["sudo", "ddcutil", "getvcp", "0xE6", "--verbose"],
                        capture_output=True, text=True, timeout=5)
for line in result.stdout.splitlines():
    if any(k in line.lower() for k in ["mh", "ml", "sh", "sl", "raw", "value"]):
        print(line.strip())

# Try I2C raw approach
# DDC/CI table write: opcode 0xE7 (table write)
print("\n=== Raw I2C probe ===")
# Read 0xE6 as raw bytes
result = subprocess.run(["sudo", "ddcutil", "getvcp", "0xE6"],
                        capture_output=True, text=True, timeout=5)
print(result.stdout.strip())

# Try: setvcp 0xE6 with value = (cmd_hi << 8 | cmd_lo)
# For read DCR: just write the command, value is don't care
print("\n=== Set 0xE6 = 0x0013 (DCR cmd) ===")
result = subprocess.run(["sudo", "ddcutil", "setvcp", "0xE6", "0x0013"],
                        capture_output=True, text=True, timeout=5)
print("stdout:", result.stdout.strip())
print("stderr:", result.stderr.strip()[:200])
print("rc:", result.returncode)

print("\n=== Read 0xE6 after ===")
result = subprocess.run(["sudo", "ddcutil", "getvcp", "0xE6", "--verbose"],
                        capture_output=True, text=True, timeout=5)
for line in result.stdout.splitlines():
    if any(k in line.lower() for k in ["mh", "ml", "sh", "sl", "raw", "value"]):
        print(line.strip())
