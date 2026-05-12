#!/usr/bin/env python3
"""Build VoiceAI widget exe."""
import os, sys, subprocess, shutil

PYTHON = r"C:\Users\a1318\AppData\Local\Programs\Python\Python311\python.exe"
if not os.path.exists(PYTHON):
    PYTHON = sys.executable

PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
DIST_DIR = os.path.join(PROJECT_DIR, "dist")
BUILD_DIR = os.path.join(PROJECT_DIR, "build_widget")
EXE_PATH = os.path.join(DIST_DIR, "VoiceAI.exe")

print("Cleaning old builds...")
for d in [DIST_DIR, BUILD_DIR]:
    if os.path.exists(d):
        shutil.rmtree(d, ignore_errors=True)

src = os.path.abspath("server.py")
static = os.path.abspath("embedded_static.py")
cmd = [
    PYTHON, "-m", "PyInstaller",
    "--name=VoiceAI",
    "--onefile",
    "--noconfirm",
    "--console",   # show console for error output
    "--distpath", DIST_DIR,
    "--workpath", BUILD_DIR,
    "--clean",
    "--add-data", f"{src};.",
    "--add-data", f"{static};.",
    "widget.py",
]
print("Running PyInstaller...")
r = subprocess.run(cmd)
if r.returncode != 0:
    print(f"[ERROR] PyInstaller failed: {r.returncode}")
    sys.exit(1)

if os.path.exists(EXE_PATH):
    size = os.path.getsize(EXE_PATH) / 1024 / 1024
    print(f"\n[SUCCESS] Built: {EXE_PATH}")
    print(f"  Size: {size:.1f} MB")
else:
    print("[ERROR] Exe not found!")
    sys.exit(1)