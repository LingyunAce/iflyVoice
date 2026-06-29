#!/usr/bin/env python3
"""Build VoiceAI widget exe.

运行方式（在项目根目录）：
    python build/build.py
    # 或在 build/ 目录下：
    cd build && python build.py
"""
import os, sys, subprocess, shutil

# 项目根 = build/ 的父目录（无论从哪里运行都正确解析）
PROJECT_DIR = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

# 优先使用固定路径的 Python，缺失时回退到当前 Python
PYTHON = r"C:\Users\a1318\AppData\Local\Programs\Python\Python311\python.exe"
if not os.path.exists(PYTHON):
    PYTHON = sys.executable

DIST_DIR = os.path.join(PROJECT_DIR, "dist")
BUILD_DIR = os.path.join(PROJECT_DIR, "build_widget")
EXE_PATH = os.path.join(DIST_DIR, "VoiceAI.exe")

print("Cleaning old builds...")
for d in [DIST_DIR, BUILD_DIR]:
    if os.path.exists(d):
        shutil.rmtree(d, ignore_errors=True)

# 资源路径（相对项目根）
WIDGET_PY = os.path.join(PROJECT_DIR, "widget.py")
SERVER_PY = os.path.join(PROJECT_DIR, "server.py")
STATIC_PY = os.path.join(PROJECT_DIR, "embedded_static.py")
VAD_ONNX = os.path.join(PROJECT_DIR, "silero_vad.onnx")

EXCLUDES = [
    # 大包，项目不依赖
    "cv2", "opencv-python",
    "scipy", "pandas", "sklearn", "scikit-learn",
    "matplotlib", "PIL", "Pillow",
    "llvmlite", "numba",
    "torch", "silero_vad",
    "av", "av.libs",
    "ctranslate2",
    "py_mini_racer",
    "lxml",
    "curl_cffi",
    "hf_xet",
    "transformers", "tokenizers",
    "torchaudio", "torchvision",
    "sympy",
    "tensorboard",
    "jinja2",
    "IPython", "ipykernel", "ipywidgets",
    "jupyter", "notebook",
    "pytest", "unittest",
    "setuptools", "distutils", "pkg_resources",
    "win32com",
    "qtpy",
    "rich", "pygments",
]
cmd = [
    PYTHON, "-m", "PyInstaller",
    "--name=VoiceAI",
    "--onefile",
    "--noconfirm",
    "--windowed",  # no console window
    "--distpath", DIST_DIR,
    "--workpath", BUILD_DIR,
    "--clean",
    "--add-data", f"{SERVER_PY};.",
    "--add-data", f"{STATIC_PY};.",
    "--add-data", f"{VAD_ONNX};.",
]
for mod in EXCLUDES:
    cmd += ["--exclude-module", mod]
cmd.append(WIDGET_PY)
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
