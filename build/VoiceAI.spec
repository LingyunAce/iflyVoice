# -*- mode: python ; coding: utf-8 -*-
# VoiceAI.spec — PyInstaller 打包配置
# 运行方式（在项目根目录）：pyinstaller build/VoiceAI.spec
# 路径使用相对路径，可在不同机器/位置复用

import os
# PyInstaller 运行 spec 时，SPEC 变量指向该 .spec 文件本身
# spec 位于 build/，所以项目根 = build/ 的父目录
PROJECT_ROOT = os.path.normpath(os.path.join(os.path.dirname(SPEC), '..'))

a = Analysis(
    [os.path.join(PROJECT_ROOT, 'widget.py')],
    pathex=[PROJECT_ROOT],
    binaries=[],
    datas=[
        (os.path.join(PROJECT_ROOT, 'server.py'), '.'),
        (os.path.join(PROJECT_ROOT, 'embedded_static.py'), '.'),
        (os.path.join(PROJECT_ROOT, 'silero_vad.onnx'), '.'),
    ],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['cv2', 'opencv-python', 'scipy', 'pandas', 'sklearn', 'scikit-learn', 'matplotlib', 'PIL', 'Pillow', 'llvmlite', 'numba', 'torch', 'silero_vad', 'av', 'av.libs', 'ctranslate2', 'py_mini_racer', 'lxml', 'curl_cffi', 'hf_xet', 'transformers', 'tokenizers', 'torchaudio', 'torchvision', 'sympy', 'tensorboard', 'jinja2', 'IPython', 'ipykernel', 'ipywidgets', 'jupyter', 'notebook', 'pytest', 'unittest', 'setuptools', 'distutils', 'pkg_resources', 'win32com', 'qtpy', 'rich', 'pygments'],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='VoiceAI',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
