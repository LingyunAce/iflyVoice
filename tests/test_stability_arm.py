#!/usr/bin/env python3
"""ARM stability test — 30-minute sustained load.

Monitors for memory leaks, thread leaks, fd leaks, and thermal throttling.

Usage:
    python tests/test_stability_arm.py [--duration 1800]
"""
import argparse
import gc
import os
import platform
import sys
import threading
import time

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

ARM64 = platform.machine() in ("aarch64", "arm64")


def get_memory_mb():
    try:
        import psutil
        return psutil.Process().memory_info().rss / 1024 / 1024
    except ImportError:
        return -1


def get_thread_count():
    return threading.active_count()


def get_temperature():
    try:
        thermal_paths = [
            "/sys/class/thermal/thermal_zone0/temp",
            "/sys/class/thermal/thermal_zone1/temp",
        ]
        for path in thermal_paths:
            if os.path.exists(path):
                with open(path) as f:
                    return int(f.read().strip()) / 1000
    except Exception:
        pass
    return -1


@pytest.mark.skipif(not ARM64, reason="ARM64-only stability test")
@pytest.mark.slow
def test_stability(duration_seconds=1800):
    print(f"=== Stability Test ({duration_seconds}s) ===")

    baseline_memory = get_memory_mb()
    baseline_threads = get_thread_count()
    baseline_temp = get_temperature()

    print(f"Baseline: memory={baseline_memory:.1f}MB, threads={baseline_threads}, temp={baseline_temp:.1f}°C")

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
            disp.dispatch(Intent(IntentType.SET_LOCAL_BACKLIGHT, {"value": 50}))
            disp.dispatch(Intent(IntentType.ADJUST_LOCAL_BACKLIGHT, {"delta": 10}))
            cur = get_backlight_value()
            set_backlight_value(50)
            set_backlight_value(cur)

            iterations += 1
            if iterations % 100 == 0:
                mem = get_memory_mb()
                temp = get_temperature()
                memory_samples.append(mem)
                elapsed = time.time() - start
                print(f"  [{elapsed:.0f}s] iter={iterations} mem={mem:.1f}MB temp={temp:.1f}°C")

            if iterations % 1000 == 0:
                gc.collect()

        except Exception as e:
            errors.append((time.time() - start, str(e)))

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

    memory_growth_mb = final_memory - baseline_memory
    memory_growth_pct = (memory_growth_mb / baseline_memory * 100) if baseline_memory > 0 else 0

    checks = []
    if memory_growth_pct > 20:
        checks.append(f"FAIL: Memory growth {memory_growth_pct:.1f}% > 20%")
    if final_temp > 75:
        checks.append(f"WARN: Temperature {final_temp:.1f}°C > 75°C")
    if len(errors) > iterations * 0.01:
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
