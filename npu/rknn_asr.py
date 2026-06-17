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
            if audio.dtype == np.float32:
                audio_int16 = (audio * 32767).astype(np.int16)
            else:
                audio_int16 = audio.astype(np.int16)

            if sample_rate != 16000:
                from scipy.signal import resample
                num_samples = int(len(audio_int16) * 16000 / sample_rate)
                audio_int16 = resample(audio_int16, num_samples).astype(np.int16)

            t0 = time.time()
            outputs = self._rknn.inference(inputs=[audio_int16])
            infer_ms = (time.time() - t0) * 1000

            self._stats["infer_time_ms"] = infer_ms
            self._stats["total_calls"] += 1

            text = self._decode_output(outputs[0])
            return text

        except Exception as e:
            _log(f"[RknnASR] Transcribe failed: {e}")
            return ""

    def _decode_output(self, output) -> str:
        """Decode model output tokens to text string.

        Placeholder — actual implementation depends on SenseVoice export format.
        """
        if isinstance(output, np.ndarray):
            return str(output.tolist()[:100])
        return str(output)[:100]

    def get_stats(self) -> dict:
        return dict(self._stats)

    def release(self):
        if self._rknn:
            self._rknn.release()
            self._loaded = False


def _log(msg):
    import sys
    print(msg, file=sys.stderr, flush=True)
