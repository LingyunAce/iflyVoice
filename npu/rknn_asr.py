"""ASR — SenseVoice-Small 推理（RKNN 优先，ONNX Runtime 兜底）

Usage:
    from npu.rknn_asr import RknnASR
    asr = RknnASR("models/sensevoice_small.rknn")  # 或 .onnx
    text = asr.transcribe(audio_numpy, sample_rate=16000)

Backend selection:
    1. .rknn 文件 → 尝试 RKNN NPU
    2. .onnx 文件 → ONNX Runtime CPU
    3. 两者都失败 → 返回空字符串
"""
from __future__ import annotations
import time
import numpy as np
from typing import Optional


class RknnASR:
    """SenseVoice-Small ASR — 支持 RKNN NPU 和 ONNX Runtime CPU 两种后端"""

    def __init__(self, model_path: str):
        self._model_path = model_path
        self._backend = None  # "rknn" or "onnx"
        self._rknn = None
        self._ort_session = None
        self._loaded = False
        self._stats = {"infer_time_ms": 0, "total_calls": 0, "backend": "none"}
        self._load_model()

    def _load_model(self):
        """Load model — try RKNN first, then ONNX Runtime"""
        path_lower = self._model_path.lower()

        # 1. 尝试 RKNN
        if path_lower.endswith('.rknn'):
            if self._load_rknn():
                return
            # .rknn 失败，尝试找对应的 .onnx 文件
            onnx_path = self._model_path.rsplit('.', 1)[0] + '.onnx'
            import os
            if os.path.exists(onnx_path):
                _log(f"[ASR] RKNN failed, trying ONNX: {onnx_path}")
                self._model_path = onnx_path
                self._load_onnx()
                return

        # 2. 尝试 ONNX Runtime（直接 .onnx 文件）
        if path_lower.endswith('.onnx'):
            self._load_onnx()

    def _load_rknn(self) -> bool:
        """Load RKNN model"""
        try:
            from rknnlite.api import RKNNLite
            self._rknn = RKNNLite()
            ret = self._rknn.load_rknn(self._model_path)
            if ret != 0:
                raise RuntimeError(f"load_rknn failed: {ret}")
            ret = self._rknn.init_runtime(core_mask=RKNNLite.NPU_CORE_0_1_2)
            if ret != 0:
                raise RuntimeError(f"init_runtime failed: {ret}")
            self._backend = "rknn"
            self._loaded = True
            self._stats["backend"] = "rknn"
            _log(f"[ASR] RKNN NPU loaded: {self._model_path}")
            return True
        except ImportError:
            _log("[ASR] rknnlite not available")
            return False
        except Exception as e:
            _log(f"[ASR] RKNN load failed: {e}")
            return False

    def _load_onnx(self) -> bool:
        """Load ONNX model with onnxruntime"""
        try:
            import onnxruntime as ort
            providers = ['CPUExecutionProvider']
            self._ort_session = ort.InferenceSession(
                self._model_path,
                providers=providers,
            )
            self._backend = "onnx"
            self._loaded = True
            self._stats["backend"] = "onnx"
            # 打印模型输入输出信息
            for inp in self._ort_session.get_inputs():
                _log(f"[ASR] ONNX input: {inp.name} {inp.shape} {inp.type}")
            for out in self._ort_session.get_outputs():
                _log(f"[ASR] ONNX output: {out.name} {out.shape} {out.type}")
            _log(f"[ASR] ONNX Runtime loaded: {self._model_path}")
            return True
        except ImportError:
            _log("[ASR] onnxruntime not available")
            return False
        except Exception as e:
            _log(f"[ASR] ONNX load failed: {e}")
            return False

    def is_loaded(self) -> bool:
        return self._loaded

    def get_backend(self) -> str:
        return self._stats.get("backend", "none")

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
            # 预处理：提取 fbank 特征
            features = self._extract_features(audio, sample_rate)
            if features is None:
                return ""

            t0 = time.time()

            if self._backend == "rknn":
                text = self._infer_rknn(features)
            elif self._backend == "onnx":
                text = self._infer_onnx(features)
            else:
                return ""

            infer_ms = (time.time() - t0) * 1000
            self._stats["infer_time_ms"] = infer_ms
            self._stats["total_calls"] += 1

            return text

        except Exception as e:
            _log(f"[ASR] Transcribe failed: {e}")
            return ""

    def _extract_features(self, audio: np.ndarray, sample_rate: int) -> Optional[np.ndarray]:
        """Extract fbank features from raw audio.

        Returns: numpy array of shape [1, seq_len, n_mels] or None on failure
        """
        try:
            # 确保是 float32
            if audio.dtype != np.float32:
                audio = audio.astype(np.float32)

            # 如果是 int16，归一化
            if audio.max() > 1.0 or audio.min() < -1.0:
                audio = audio / 32768.0

            # 重采样到 16kHz
            if sample_rate != 16000:
                try:
                    import librosa
                    audio = librosa.resample(audio, orig_sr=sample_rate, target_sr=16000)
                except ImportError:
                    # 简单线性插值重采样
                    ratio = 16000 / sample_rate
                    new_len = int(len(audio) * ratio)
                    audio = np.interp(
                        np.linspace(0, len(audio), new_len, endpoint=False),
                        np.arange(len(audio)),
                        audio
                    )

            # 提取 fbank 特征
            try:
                import librosa
                # librosa mel spectrogram
                mel_spec = librosa.feature.melspectrogram(
                    y=audio, sr=16000, n_mels=80, n_fft=512, hop_length=160, win_length=400
                )
                log_mel = librosa.power_to_db(mel_spec, ref=np.max)
                # 转置为 [seq_len, n_mels]
                features = log_mel.T
            except ImportError:
                # 无 librosa 时用简单的 STFT + mel filterbank
                features = self._simple_fbank(audio, sr=16000, n_mels=80)

            # CMVN 归一化
            mean = features.mean(axis=0, keepdims=True)
            std = features.std(axis=0, keepdims=True) + 1e-8
            features = (features - mean) / std

            # 添加 batch 维度: [1, seq_len, n_mels]
            features = features[np.newaxis, :, :].astype(np.float32)
            return features

        except Exception as e:
            _log(f"[ASR] Feature extraction failed: {e}")
            return None

    def _simple_fbank(self, audio: np.ndarray, sr: int = 16000,
                      n_fft: int = 512, hop_length: int = 160,
                      n_mels: int = 80) -> np.ndarray:
        """Simple fbank feature extraction without librosa"""
        # STFT
        from numpy.lib.stride_tricks import as_strided
        n_frames = 1 + (len(audio) - n_fft) // hop_length
        # 简化：直接用 numpy 实现
        frames = np.zeros((n_frames, n_fft))
        for i in range(n_frames):
            start = i * hop_length
            frames[i] = audio[start:start + n_fft] * np.hanning(n_fft)

        # FFT
        spec = np.abs(np.fft.rfft(frames, n=n_fft))

        # Mel filterbank (简化版)
        low_freq_mel = 0
        high_freq_mel = 2595 * np.log10(1 + (sr / 2) / 700)
        mel_points = np.linspace(low_freq_mel, high_freq_mel, n_mels + 2)
        hz_points = 700 * (10 ** (mel_points / 2595) - 1)
        bin_points = np.floor((n_fft + 1) * hz_points / sr).astype(int)

        fbank = np.zeros((n_mels, n_fft // 2 + 1))
        for m in range(n_mels):
            f_left = bin_points[m]
            f_center = bin_points[m + 1]
            f_right = bin_points[m + 2]
            for k in range(f_left, f_center):
                if f_center != f_left:
                    fbank[m, k] = (k - f_left) / (f_center - f_left)
            for k in range(f_center, f_right):
                if f_right != f_center:
                    fbank[m, k] = (f_right - k) / (f_right - f_center)

        # Apply filterbank
        mel_spec = np.dot(spec, fbank.T)
        # Log
        mel_spec = np.log(mel_spec + 1e-8)
        return mel_spec

    def _infer_rknn(self, features: np.ndarray) -> str:
        """RKNN inference"""
        outputs = self._rknn.inference(inputs=[features])
        return self._decode_output(outputs[0])

    def _infer_onnx(self, features: np.ndarray) -> str:
        """ONNX Runtime inference"""
        session = self._ort_session
        input_names = [inp.name for inp in session.get_inputs()]

        # 构建输入 — 根据模型实际类型（int32 vs int64）
        feed = {}
        for inp in session.get_inputs():
            name = inp.name
            dtype_str = inp.type  # e.g. "tensor(int32)", "tensor(float)"
            if 'speech' in name.lower() and 'length' not in name.lower():
                feed[name] = features
            elif 'length' in name.lower():
                # speech_lengths
                if 'int32' in dtype_str:
                    feed[name] = np.array([features.shape[1]], dtype=np.int32)
                else:
                    feed[name] = np.array([features.shape[1]], dtype=np.int64)
            elif 'language' in name.lower():
                # 语言：中文=0, 英文=1, 日文=2, 粤语=3, 韩文=4
                if 'int32' in dtype_str:
                    feed[name] = np.array([0], dtype=np.int32)
                else:
                    feed[name] = np.array([0], dtype=np.int64)
            elif 'textnorm' in name.lower():
                # 文本规范化：2=基础
                if 'int32' in dtype_str:
                    feed[name] = np.array([2], dtype=np.int32)
                else:
                    feed[name] = np.array([2], dtype=np.int64)

        outputs = session.run(None, feed)

        # CTC 解码
        logits = outputs[0]  # [batch, seq, vocab]
        return self._decode_ctc(logits)

    def _decode_ctc(self, logits: np.ndarray) -> str:
        """CTC greedy decoding"""
        # logits: [batch, seq, vocab]
        if logits.ndim == 3:
            logits = logits[0]  # [seq, vocab]

        # argmax
        token_ids = np.argmax(logits, axis=-1)

        # CTC 去重 + 去 blank (假设 blank=0)
        prev = -1
        ids = []
        for tid in token_ids:
            if tid != 0 and tid != prev:  # 0 = blank
                ids.append(int(tid))
            prev = tid

        # 用 tokenizer 解码
        try:
            import json
            import os
            tokens_path = os.path.join(os.path.dirname(self._model_path), '..', 'tokens.json')
            if not os.path.exists(tokens_path):
                tokens_path = os.path.join(os.path.dirname(self._model_path), 'tokens.json')
            if os.path.exists(tokens_path):
                with open(tokens_path, 'r', encoding='utf-8') as f:
                    tokens = json.load(f)
                # tokens 是 dict: {token_str: id}
                id_to_token = {v: k for k, v in tokens.items()}
                text = ''.join(id_to_token.get(tid, '') for tid in ids)
                return text
        except Exception as e:
            _log(f"[ASR] Token decode failed: {e}")

        # 无 tokenizer 时返回 token id 列表
        return f"[tokens:{ids[:50]}]"

    def _decode_output(self, output) -> str:
        """Decode model output tokens to text string (RKNN 用)"""
        if isinstance(output, np.ndarray):
            if output.ndim >= 2:
                return self._decode_ctc(output)
            return str(output.tolist()[:100])
        return str(output)[:100]

    def get_stats(self) -> dict:
        return dict(self._stats)

    def release(self):
        if self._rknn:
            try:
                self._rknn.release()
            except Exception:
                pass
        self._ort_session = None
        self._loaded = False


def _log(msg):
    import sys
    print(msg, file=sys.stderr, flush=True)
