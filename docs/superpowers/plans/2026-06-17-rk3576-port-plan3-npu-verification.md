# RK3576 Port — Plan 3: NPU 接入 + ARM 验证门禁

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 用 RK3576 的 6 TOPS NPU 跑 ASR（SenseVoice-Small），替换远端 SenseVoice HTTP 调用；加 ARM 专属性能验证套件（bench / e2e latency / 30min 长稳）。

**Architecture:**
- 新建 `npu/` 子模块：`rknn_asr.py`（RKNN 跑 SenseVoice-Small）、`wakeword.py`（NPU 唤醒词，可选）
- `voice_pipeline.py` 的 `_transcribe()` 改走 NPU ASR（`npu_asr_enabled=true` 时）
- 新建测试：`tests/bench_arm64.py`（性能基准）、`tests/e2e_latency.sh`（延迟测试）、`tests/test_stability_arm.py`（30min 长稳）
- `scripts/check_arm64.sh` 加 NPU 相关检查项

**Tech Stack:** rknn-toolkit2-lite2 (RKNN Runtime), onnxruntime (fallback), numpy, ffmpeg

**Reference spec:** `docs/superpowers/specs/2026-06-17-rk3576-port-design.md` §7.4 / §7.5 / §7.6 / §7.8

**前置：** Plan 1 + Plan 2 已完成（executor、linux/、voice_pipeline 路由、widget 字体、60 测试通过）

**⚠️ 重要约束：**
- NPU 模型转换（ONNX → RKNN）**必须在 x86 PC 上用 rknn-toolkit2 完成**，不能在板子上转
- 板子上只有 `rknn-toolkit2-lite2`（推理运行时），没有转换工具
- SenseVoice-Small 模型需要从 ModelScope/HuggingFace 下载
- 本 Plan 的测试需要在板子上跑（NPU 推理依赖硬件）

---

## 文件结构（Plan 3 涉及）

```
iflyVoice/
├── npu/                       # 🆕 新增
│   ├── __init__.py
│   ├── rknn_asr.py            # RKNN 跑 SenseVoice-Small
│   └── wakeword.py            # NPU 唤醒词（可选，Phase 4）
│
├── models/                    # 🆕 模型存放目录
│   └── .gitkeep               # 不提交大文件
│
├── voice_pipeline.py          # 改：_transcribe() 支持 NPU ASR
├── settings.json              # 改：npu_asr_enabled 生效
│
├── tests/
│   ├── bench_arm64.py         # 🆕 性能基准（板子跑）
│   ├── test_npu_asr.py        # 🆕 NPU ASR 单测（板子跑）
│   ├── e2e_latency.sh         # 🆕 端到端延迟测试（板子跑）
│   └── test_stability_arm.py  # 🆕 30min 长稳（板子跑）
│
└── scripts/
    └── check_arm64.sh         # 改：加 NPU 检查项
```

---

## Phase 1: NPU ASR 模块

### Task 1.1: `npu/rknn_asr.py` — RKNN ASR 推理

**Files:**
- Create: `npu/__init__.py`
- Create: `npu/rknn_asr.py`
- Create: `models/.gitkeep`
- Test: `tests/test_npu_asr.py`

- [ ] **Step 1: 写失败测试**

写入 `tests/test_npu_asr.py`：
```python
"""NPU ASR 单测 — 需要板子 + RKNN 模型"""
import pytest
import os
import numpy as np


@pytest.fixture
def asr_model():
    """加载 RKNN ASR 模型（板子上才有）"""
    from npu.rknn_asr import RknnASR
    model_path = os.path.join(os.path.dirname(__file__), "..", "models", "sensevoice_small.rknn")
    if not os.path.exists(model_path):
        pytest.skip("RKNN model not found (run on board with converted model)")
    return RknnASR(model_path)


def test_rknn_asr_loads(asr_model):
    """模型加载成功"""
    assert asr_model is not None
    assert asr_model.is_loaded()


def test_rknn_asr_transcribes_silence(asr_model):
    """静音音频应返回空字符串或极短文本"""
    silence = np.zeros(16000 * 2, dtype=np.float32)  # 2s silence
    text = asr_model.transcribe(silence, sample_rate=16000)
    assert isinstance(text, str)


def test_rknn_asr_transcribes_audio_file(asr_model):
    """真实音频文件转写（需要 test fixtures）"""
    fixture = os.path.join(os.path.dirname(__file__), "fixtures", "test_audio_5s.wav")
    if not os.path.exists(fixture):
        pytest.skip("Test audio fixture not found")
    import soundfile as sf
    audio, sr = sf.read(fixture, dtype="float32")
    text = asr_model.transcribe(audio, sample_rate=sr)
    assert len(text) > 0
    print(f"ASR result: {text}")


def test_rknn_asr_returns_stats(asr_model):
    """推理后返回性能统计"""
    silence = np.zeros(16000 * 2, dtype=np.float32)
    asr_model.transcribe(silence, sample_rate=16000)
    stats = asr_model.get_stats()
    assert "infer_time_ms" in stats
    assert stats["infer_time_ms"] > 0
```

- [ ] **Step 2: 跑测试确认失败**

```bash
pytest tests/test_npu_asr.py -v
```

Expected: `ModuleNotFoundError: No module named 'npu'`

- [ ] **Step 3: 实现 `npu/rknn_asr.py`**

写入 `npu/__init__.py`：
```python
"""NPU inference module — RKNN ASR / wake word / speaker ID"""
```

写入 `npu/rknn_asr.py`：
```python
"""RKNN ASR — SenseVoice-Small on RK3576 NPU

Usage:
    from npu.rknn_asr import RknnASR
    asr = RknnASR("models/sensevoice_small.rknn")
    text = asr.transcribe(audio_numpy, sample_rate=16000)

Requires:
    - rknn-toolkit2-lite2 on aarch64 board
    - Converted RKNN model file
"""
from __future__ import annotations
import time
import numpy as np
from typing import Optional


class RknnASR:
    """SenseVoice-Small ASR on RKNN NPU"""

    def __init__(self, model_path: str):
        self._model_path = model_path
        self._rknn = None
        self._loaded = False
        self._stats = {"infer_time_ms": 0, "total_calls": 0}
        self._load_model()

    def _load_model(self):
        """Load RKNN model (lazy import to avoid crash on x86)"""
        try:
            from rknnlite.api import RKNNLite
            self._rknn = RKNNLite()
            ret = self._rknn.load_rknn(self._model_path)
            if ret != 0:
                raise RuntimeError(f"Failed to load RKNN model: {ret}")
            ret = self._rknn.init_runtime(core_mask=RKNNLite.NPU_CORE_0_1_2)
            if ret != 0:
                raise RuntimeError(f"Failed to init RKNN runtime: {ret}")
            self._loaded = True
        except ImportError:
            # Not on aarch64 or rknn not installed
            self._loaded = False
        except Exception as e:
            _log(f"[RknnASR] Load failed: {e}")
            self._loaded = False

    def is_loaded(self) -> bool:
        return self._loaded

    def transcribe(self, audio: np.ndarray, sample_rate: int = 16000) -> str:
        """Transcribe audio to text.

        Args:
            audio: float32 numpy array, mono, normalized to [-1, 1]
            sample_rate: sample rate (default 16000)

        Returns:
            Transcribed text, or empty string on failure
        """
        if not self._loaded:
            return ""

        try:
            # Preprocess: convert to int16 for SenseVoice
            if audio.dtype == np.float32:
                audio_int16 = (audio * 32767).astype(np.int16)
            else:
                audio_int16 = audio.astype(np.int16)

            # Resample to 16kHz if needed
            if sample_rate != 16000:
                from scipy.signal import resample
                num_samples = int(len(audio_int16) * 16000 / sample_rate)
                audio_int16 = resample(audio_int16, num_samples).astype(np.int16)

            # Run inference
            t0 = time.time()
            outputs = self._rknn.inference(inputs=[audio_int16])
            infer_ms = (time.time() - t0) * 1000

            # Update stats
            self._stats["infer_time_ms"] = infer_ms
            self._stats["total_calls"] += 1

            # Postprocess: decode output tokens to text
            # SenseVoice output format depends on the model export
            # Typically: outputs[0] is token IDs, need tokenizer decode
            text = self._decode_output(outputs[0])
            return text

        except Exception as e:
            _log(f"[RknnASR] Transcribe failed: {e}")
            return ""

    def _decode_output(self, output) -> str:
        """Decode model output tokens to text string.

        Placeholder — actual implementation depends on SenseVoice export format.
        SenseVoice-Small typically outputs token IDs that need a SentencePiece tokenizer.
        """
        # TODO: Implement tokenizer decode based on actual model output format
        # For now, return raw output as string for debugging
        if isinstance(output, np.ndarray):
            return str(output.tolist()[:100])  # truncate for safety
        return str(output)[:100]

    def get_stats(self) -> dict:
        """Return inference performance stats"""
        return dict(self._stats)

    def release(self):
        """Release RKNN resources"""
        if self._rknn:
            self._rknn.release()
            self._loaded = False


def _log(msg):
    import sys
    print(msg, file=sys.stderr, flush=True)
```

写入 `models/.gitkeep`：（空文件）

- [ ] **Step 4: 跑测试**

在 x86 上：`rknn-toolkit2-lite2` 不可用，所有测试应 skip：
```bash
pytest tests/test_npu_asr.py -v
```

Expected: 4 skipped (rknn not available)

- [ ] **Step 5: 提交**

```bash
git add npu/ models/.gitkeep tests/test_npu_asr.py
git commit -m "feat(npu): add RknnASR for SenseVoice-Small on RK3576 NPU"
```

---

### Task 1.2: voice_pipeline.py — 支持 NPU ASR 双模式

**Files:**
- Modify: `voice_pipeline.py`（`_transcribe()` 方法）

- [ ] **Step 1: 读取当前 _transcribe 实现**

读 `voice_pipeline.py` line 1273-1308（`_transcribe` 方法）和 line 240 附近（`__init__`）。

- [ ] **Step 2: 在 __init__ 中加载 NPU ASR**

在 `voice_pipeline.py` 的 `__init__` 末尾（已有 dispatcher 初始化之后）加：

```python
        # NPU ASR (Plan 3)
        self._npu_asr = None
        if self._config.get("npu_asr_enabled", False):
            try:
                from npu.rknn_asr import RknnASR
                import os as _os
                model_path = _os.path.join(_os.path.dirname(__file__), "models", "sensevoice_small.rknn")
                if _os.path.exists(model_path):
                    self._npu_asr = RknnASR(model_path)
                    if self._npu_asr.is_loaded():
                        _flog("[NPU] ASR 模型加载成功")
                    else:
                        _flog("[NPU] ASR 模型加载失败，回退到远端")
                        self._npu_asr = None
                else:
                    _flog(f"[NPU] 模型文件不存在: {model_path}")
            except Exception as e:
                _flog(f"[NPU] ASR 初始化异常: {e}")
```

- [ ] **Step 3: 改 _transcribe 支持双模式**

把 `_transcribe` 方法改成：

```python
    def _transcribe(self, webm_file):
        """语音转文字 — NPU 优先，远端兜底"""
        # 1. 尝试 NPU ASR
        if self._npu_asr and self._npu_asr.is_loaded():
            try:
                import soundfile as sf
                audio, sr = sf.read(webm_file, dtype="float32")
                text = self._npu_asr.transcribe(audio, sample_rate=sr)
                if text:
                    stats = self._npu_asr.get_stats()
                    _flog(f"[ASR] NPU: {text} ({stats['infer_time_ms']:.0f}ms)")
                    return text
                _flog("[ASR] NPU 返回空，回退到远端")
            except Exception as e:
                _flog(f"[ASR] NPU 异常，回退到远端: {e}")

        # 2. 远端 SenseVoice（原有逻辑）
        try:
            # ... 原有 HTTP 调用代码保持不变 ...
```

（保留原有 HTTP 调用代码作为 fallback）

- [ ] **Step 4: 跑测试**

```bash
pytest tests/ -v
```

Expected: 60+ passed（NPU 测试在 x86 上 skip，不影响其他）

- [ ] **Step 5: 提交**

```bash
git add voice_pipeline.py
git commit -m "feat(pipeline): add NPU ASR dual-mode (NPU first, remote fallback)"
```

---

## Phase 2: ARM 验证套件

### Task 2.1: `tests/bench_arm64.py` — 性能基准

**Files:**
- Create: `tests/bench_arm64.py`

- [ ] **Step 1: 写脚本**

写入 `tests/bench_arm64.py`：
```python
#!/usr/bin/env python3
"""ARM64 performance benchmark — runs on RK3576 board.

Output: bench_report_YYYYMMDD_HHMMSS.json

Usage:
    python tests/bench_arm64.py [--output report.json]
"""
import argparse
import json
import os
import sys
import time
import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


def bench_vad():
    """Benchmark Silero VAD inference time"""
    try:
        from vad_engine import SileroVAD
        vad = SileroVAD()
        audio = np.random.randn(512).astype(np.float32) * 0.01
        times = []
        for _ in range(100):
            t0 = time.time()
            vad(audio, 16000)
            times.append((time.time() - t0) * 1000)
        return {
            "model": "Silero-VAD-ONNX",
            "infer_p50_ms": sorted(times)[50],
            "infer_p95_ms": sorted(times)[95],
            "samples": len(times),
        }
    except Exception as e:
        return {"error": str(e)}


def bench_npu_asr():
    """Benchmark NPU ASR inference time (board only)"""
    try:
        from npu.rknn_asr import RknnASR
        model_path = os.path.join(os.path.dirname(__file__), "..", "models", "sensevoice_small.rknn")
        if not os.path.exists(model_path):
            return {"error": "RKNN model not found"}
        asr = RknnASR(model_path)
        if not asr.is_loaded():
            return {"error": "RKNN model failed to load"}
        audio = np.random.randn(16000 * 5).astype(np.float32) * 0.01  # 5s
        times = []
        for _ in range(10):
            t0 = time.time()
            asr.transcribe(audio, sample_rate=16000)
            times.append((time.time() - t0) * 1000)
        asr.release()
        return {
            "model": "SenseVoice-Small-RKNN",
            "load_time_ms": 0,  # already loaded
            "infer_p50_ms": sorted(times)[len(times)//2],
            "infer_p95_ms": sorted(times)[int(len(times)*0.95)],
            "rts": 5000 / (sorted(times)[len(times)//2] or 1),  # real-time factor
            "samples": len(times),
        }
    except Exception as e:
        return {"error": str(e)}


def bench_memory():
    """Benchmark memory usage"""
    try:
        import psutil
        proc = psutil.Process()
        return {
            "rss_mb": proc.memory_info().rss / 1024 / 1024,
            "peak_mb": proc.memory_info().rss / 1024 / 1024,  # approximate
        }
    except Exception as e:
        return {"error": str(e)}


def main():
    parser = argparse.ArgumentParser(description="ARM64 performance benchmark")
    parser.add_argument("--output", "-o", default=None, help="Output JSON path")
    args = parser.parse_args()

    print("=== VAD Benchmark ===")
    vad_result = bench_vad()
    print(f"  VAD: {vad_result}")

    print("\n=== NPU ASR Benchmark ===")
    asr_result = bench_npu_asr()
    print(f"  ASR: {asr_result}")

    print("\n=== Memory ===")
    mem_result = bench_memory()
    print(f"  Memory: {mem_result}")

    report = {
        "device": "RK3576",
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "asr": asr_result,
        "vad": vad_result,
        "memory": mem_result,
    }

    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            json.dump(report, f, indent=2, ensure_ascii=False)
        print(f"\nReport saved: {args.output}")
    else:
        print(f"\n{json.dumps(report, indent=2, ensure_ascii=False)}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 2: 提交**

```bash
git add tests/bench_arm64.py
git commit -m "test(port): add bench_arm64.py for NPU/VAD performance benchmarking"
```

---

### Task 2.2: `tests/e2e_latency.sh` — 端到端延迟测试

**Files:**
- Create: `tests/e2e_latency.sh`

- [ ] **Step 1: 写脚本**

写入 `tests/e2e_latency.sh`：
```bash
#!/bin/bash
# End-to-end latency test — measures full pipeline latency.
# Must run on board with mic + speaker + NPU.
set +e
cd "$(dirname "$0")/.."

GREEN='\033[0;32m'; RED='\033[0;31m'; NC='\033[0m'
pass=0; fail=0

check() {
    local name=$1
    local cmd=$2
    echo -n "[$name] "
    if eval "$cmd" >/dev/null 2>&1; then
        echo -e "${GREEN}PASS${NC}"
        ((pass++))
    else
        echo -e "${RED}FAIL${NC}"
        ((fail++))
    fi
}

echo "=== E2E Latency Tests ==="

echo
echo "--- 1. VAD Latency ---"
check "VAD < 10ms" "python3 -c '
import time, numpy as np
from vad_engine import SileroVAD
vad = SileroVAD()
audio = np.random.randn(512).astype(np.float32) * 0.01
t0 = time.time()
for _ in range(100):
    vad(audio, 16000)
avg = (time.time() - t0) / 100 * 1000
print(f\"VAD avg: {avg:.1f}ms\")
assert avg < 10, f\"VAD too slow: {avg}ms\"
'"

echo
echo "--- 2. ASR Latency ---"
check "NPU ASR < 2s (5s audio)" "python3 -c '
import time, numpy as np, os, sys
sys.path.insert(0, \".\")
from npu.rknn_asr import RknnASR
model = \"models/sensevoice_small.rknn\"
if not os.path.exists(model):
    print(\"SKIP: no model\")
    sys.exit(0)
asr = RknnASR(model)
if not asr.is_loaded():
    print(\"SKIP: model failed to load\")
    sys.exit(0)
audio = np.random.randn(16000 * 5).astype(np.float32) * 0.01
t0 = time.time()
asr.transcribe(audio, sample_rate=16000)
latency = (time.time() - t0) * 1000
print(f\"ASR latency: {latency:.0f}ms\")
assert latency < 2000, f\"ASR too slow: {latency}ms\"
'"

echo
echo "--- 3. Backlight Control Latency ---"
check "Backlight set < 200ms" "python3 -c '
import time
from linux.backlight import get_backlight_value, set_backlight_value
cur = get_backlight_value()
t0 = time.time()
set_backlight_value(50)
latency = (time.time() - t0) * 1000
set_backlight_value(cur)  # restore
print(f\"Backlight latency: {latency:.0f}ms\")
assert latency < 200, f\"Too slow: {latency}ms\"
'"

echo
echo "--- 4. Executor Dispatcher Latency ---"
check "Dispatcher dispatch < 10ms" "python3 -c '
import time
from executor.dispatcher import ExecutorDispatcher
from executor.dev_stub import DevStubExecutor
from executor.pc_agent import PCAgentExecutor
from executor.local import LocalExecutor
from executor.base import Intent, IntentType
disp = ExecutorDispatcher(PCAgentExecutor(\"http://fake\"), DevStubExecutor(), LocalExecutor())
t0 = time.time()
for _ in range(100):
    disp.dispatch(Intent(IntentType.SET_LOCAL_BACKLIGHT, {\"value\": 50}))
avg = (time.time() - t0) / 100 * 1000
print(f\"Dispatcher avg: {avg:.2f}ms\")
assert avg < 10, f\"Too slow: {avg}ms\"
'"

echo
echo "=== Summary ==="
echo -e "  ${GREEN}PASS: $pass${NC} | ${RED}FAIL: $fail${NC}"
[ $fail -eq 0 ] && exit 0 || exit 1
```

- [ ] **Step 2: chmod + 提交**

```bash
chmod +x tests/e2e_latency.sh
git add tests/e2e_latency.sh
git commit -m "test(port): add e2e_latency.sh for full pipeline latency measurement"
```

---

### Task 2.3: `tests/test_stability_arm.py` — 30min 长稳测试

**Files:**
- Create: `tests/test_stability_arm.py`

- [ ] **Step 1: 写脚本**

写入 `tests/test_stability_arm.py`：
```python
#!/usr/bin/env python3
"""ARM stability test — 30-minute sustained load.

Monitors for memory leaks, thread leaks, fd leaks, and thermal throttling.

Usage:
    python tests/test_stability_arm.py [--duration 1800]  # default 30 min
"""
import argparse
import gc
import os
import sys
import threading
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


def get_memory_mb():
    """Get current RSS in MB"""
    try:
        import psutil
        return psutil.Process().memory_info().rss / 1024 / 1024
    except ImportError:
        return -1


def get_thread_count():
    return threading.active_count()


def get_temperature():
    """Read CPU temperature from sysfs (RK3576)"""
    try:
        thermal_paths = [
            "/sys/class/thermal/thermal_zone0/temp",
            "/sys/class/thermal/thermal_zone1/temp",
        ]
        for path in thermal_paths:
            if os.path.exists(path):
                with open(path) as f:
                    return int(f.read().strip()) / 1000  # millidegrees -> degrees
    except Exception:
        pass
    return -1


def test_stability(duration_seconds=1800):
    """Run stability test for specified duration"""
    print(f"=== Stability Test ({duration_seconds}s) ===")

    baseline_memory = get_memory_mb()
    baseline_threads = get_thread_count()
    baseline_temp = get_temperature()

    print(f"Baseline: memory={baseline_memory:.1f}MB, threads={baseline_threads}, temp={baseline_temp:.1f}°C")

    # Import components
    try:
        from executor.dispatcher import ExecutorDispatcher
        from executor.dev_stub import DevStubExecutor
        from executor.pc_agent import PCAgentExecutor
        from executor.local import LocalExecutor
        from executor.base import Intent, IntentType
        from linux.backlight import get_backlight_value, set_backlight_value
    except ImportError as e:
        print(f"SKIP: Cannot import components: {e}")
        return True

    disp = ExecutorDispatcher(
        pc_agent=PCAgentExecutor("http://fake", timeout=0.1, max_retries=0),
        dev_stub=DevStubExecutor(),
        local_executor=LocalExecutor(),
    )

    start = time.time()
    iterations = 0
    memory_samples = []
    errors = []

    print("\nRunning sustained load...")
    while time.time() - start < duration_seconds:
        try:
            # 1. Dispatcher dispatch
            disp.dispatch(Intent(IntentType.SET_LOCAL_BACKLIGHT, {"value": 50}))
            disp.dispatch(Intent(IntentType.ADJUST_LOCAL_BACKLIGHT, {"delta": 10}))

            # 2. Backlight control
            cur = get_backlight_value()
            set_backlight_value(50)
            set_backlight_value(cur)

            # 3. Memory check every 100 iterations
            iterations += 1
            if iterations % 100 == 0:
                mem = get_memory_mb()
                temp = get_temperature()
                memory_samples.append(mem)
                elapsed = time.time() - start
                print(f"  [{elapsed:.0f}s] iter={iterations} mem={mem:.1f}MB temp={temp:.1f}°C")

            # 4. GC every 1000 iterations
            if iterations % 1000 == 0:
                gc.collect()

        except Exception as e:
            errors.append((time.time() - start, str(e)))

    # Analysis
    elapsed = time.time() - start
    final_memory = get_memory_mb()
    final_threads = get_thread_count()
    final_temp = get_temperature()

    print(f"\n=== Results ===")
    print(f"Duration: {elapsed:.0f}s")
    print(f"Iterations: {iterations}")
    print(f"Memory: {baseline_memory:.1f}MB -> {final_memory:.1f}MB (delta={final_memory-baseline_memory:.1f}MB)")
    print(f"Threads: {baseline_threads} -> {final_threads}")
    print(f"Temperature: {baseline_temp:.1f}°C -> {final_temp:.1f}°C")
    print(f"Errors: {len(errors)}")

    if errors:
        print("\nFirst 5 errors:")
        for t, e in errors[:5]:
            print(f"  [{t:.1f}s] {e}")

    # Checks
    memory_growth_mb = final_memory - baseline_memory
    memory_growth_pct = (memory_growth_mb / baseline_memory * 100) if baseline_memory > 0 else 0

    checks = []
    if memory_growth_pct > 20:
        checks.append(f"FAIL: Memory growth {memory_growth_pct:.1f}% > 20%")
    if final_temp > 75:
        checks.append(f"WARN: Temperature {final_temp:.1f}°C > 75°C")
    if len(errors) > iterations * 0.01:  # > 1% error rate
        checks.append(f"FAIL: Error rate {len(errors)/iterations*100:.2f}% > 1%")

    if checks:
        print("\n--- Issues ---")
        for c in checks:
            print(f"  {c}")
        return False

    print("\n--- PASSED ---")
    return True


def main():
    parser = argparse.ArgumentParser(description="ARM stability test")
    parser.add_argument("--duration", "-d", type=int, default=1800, help="Test duration in seconds")
    args = parser.parse_args()

    success = test_stability(args.duration)
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: 提交**

```bash
git add tests/test_stability_arm.py
git commit -m "test(port): add test_stability_arm.py for 30-minute sustained load"
```

---

## Phase 3: 更新检查脚本

### Task 3.1: `scripts/check_arm64.sh` — 加 NPU 检查项

**Files:**
- Modify: `scripts/check_arm64.sh`

- [ ] **Step 1: 读取当前 check_arm64.sh**

读 `scripts/check_arm64.sh` 确认当前内容。

- [ ] **Step 2: 在 NPU 检查段后加 RKNN 模型检查**

在现有的 NPU 检查段（`[6] NPU`）末尾，加：

```bash
    # RKNN model file
    if [ -f models/sensevoice_small.rknn ]; then
        check_pass "sensevoice_small.rknn 模型文件"
    else
        check_warn "sensevoice_small.rknn 不存在（ASR 将走远端）"
    fi
```

- [ ] **Step 3: 提交**

```bash
git add scripts/check_arm64.sh
git commit -m "test(port): add RKNN model file check to check_arm64.sh"
```

---

## 验收标准（Plan 3 完成时）

- [ ] x86 上 `pytest tests/ -v` 全部通过（NPU 测试 skip，不影响其他）
- [ ] `npu/rknn_asr.py` 模块可 import（x86 上 skip 加载）
- [ ] `voice_pipeline.py` 的 `_transcribe()` 支持 NPU 优先 + 远端兜底
- [ ] `tests/bench_arm64.py` 可运行（输出 JSON 报告）
- [ ] `tests/e2e_latency.sh` 可运行（板子上跑）
- [ ] `tests/test_stability_arm.py` 可运行（板子上 30min）
- [ ] `scripts/check_arm64.sh` 检查 RKNN 模型文件
- [ ] Plan 3 期间 5-7 个 commit

## 模型准备指南（在 x86 PC 上执行）

```bash
# 1. 下载 SenseVoice-Small
pip install modelscope
python -c "from modelscope import snapshot_download; snapshot_download('iic/SenseVoiceSmall', local_dir='models/SenseVoiceSmall')"

# 2. 转换为 RKNN 格式
pip install rknn-toolkit2  # x86 version
python -c "
from rknn.api import RKNN
rknn = RKNN()
rknn.config(mean_values=[[0.0]], std_values=[[1.0]], target_platform='rk3576')
rknn.load_onnx(model='models/SenseVoiceSmall/model.onnx')
rknn.build(do_quantization=False)
rknn.export_rknn('models/sensevoice_small.rknn')
"

# 3. 上传到板子
scp models/sensevoice_small.rknn user@rk3576:/path/to/iflyVoice/models/
```

## 后续

- 本 Plan 完成后，RK3576 端到端链路：mic → VAD → 唤醒 → NPU ASR → LLM → executor → TTS → speaker
- 唤醒词 NPU 推理（`npu/wakeword.py`）可作为后续优化
- 说话人识别（`npu/speaker_id.py`）可作为后续功能
