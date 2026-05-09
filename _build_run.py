"""Compile and run C# volume reader - handles GBK encoding issues"""
import subprocess
import os
import sys

CSC = r"C:\Windows\Microsoft.NET\Framework64\v4.0.30319\csc.exe"
BASE = r"C:\Users\a1318\WorkBuddy\xunfei_yuyin\iflyVoice"
SRC = os.path.join(BASE, "_vol_test.cs")
EXE = os.path.join(BASE, "_vol_read.exe")
OUT_LOG = os.path.join(BASE, "_vol_log.txt")

def run(cmd, timeout=30):
    """Run command with safe encoding"""
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    result = subprocess.run(cmd, capture_output=True, timeout=timeout,
                          errors="replace", env=env)
    return result

# Step 1: Compile
print("Compiling...")
r = run([CSC, "/target:exe", f"/out:{EXE}", "/nologo", SRC])
with open(OUT_LOG, "w", encoding="utf-8") as f:
    f.write(f"COMPILE exit={r.returncode}\nstdout={r.stdout[:500]}\nstderr={r.stderr[:500]}\n")

print(f"Compile exit={r.returncode}")
if not os.path.exists(EXE):
    print("COMPILE FAILED - see _vol_log.txt")
    sys.exit(1)
print("Compiled OK")

# Step 2: Run
print("\nRunning volume reader...")
r2 = run([EXE], timeout=10)

with open(OUT_LOG, "a", encoding="utf-8") as f:
    f.write(f"\nRUN exit={r2.returncode}\nstdout=[{r2.stdout}]\nstderr=[{r2.stderr}]\n")

print(f"Run exit={r2.returncode}")
print(f"stdout=[{r2.stdout}]")
print(f"stderr=[{r2.stderr}]")

# Parse result
out = r2.stdout.strip()
if out.lstrip('-').isdigit():
    vol = int(out)
    if vol >= 0 and vol <= 100:
        print(f"\n>>> SUCCESS: System master volume = {vol}% <<<")
    else:
        print(f"\n>>> Error code: {vol} <<<")
