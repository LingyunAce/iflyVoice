# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['widget.py'],
    pathex=[],
    binaries=[],
    datas=[('C:\\Users\\a1318\\WorkBuddy\\xunfei_yuyin\\iflyVoice\\server.py', '.'), ('C:\\Users\\a1318\\WorkBuddy\\xunfei_yuyin\\iflyVoice\\embedded_static.py', '.'), ('C:\\Users\\a1318\\WorkBuddy\\xunfei_yuyin\\iflyVoice\\silero_vad.onnx', '.')],
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
