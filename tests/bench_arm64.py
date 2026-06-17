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
        audio = np.random.randn(16000 * 5).astype(np.float32) * 0.01
        times = []
        for _ in range(10):
            t0 = time.time()
            asr.transcribe(audio, sample_rate=16000)
            times.append((time.time() - t0) * 1000)
        asr.release()
        return {
            "model": "SenseVoice-Small-RKNN",
            "load_time_ms": 0,
            "infer_p50_ms": sorted(times)[len(times)//2],
            "infer_p95_ms": sorted(times)[int(len(times)*0.95)],
            "rts": 5000 / (sorted(times)[len(times)//2] or 1),
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
            "peak_mb": proc.memory_info().rss / 1024 / 1024,
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
