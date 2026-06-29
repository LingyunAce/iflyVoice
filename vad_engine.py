"""Silero VAD engine — 纯 numpy + onnxruntime，不依赖 PyTorch"""
import os
import numpy as np
import onnxruntime


class SileroVAD:
    def __init__(self, model_path=None):
        if model_path is None:
            model_path = os.path.join(os.path.dirname(__file__), "silero_vad.onnx")
        opts = onnxruntime.SessionOptions()
        opts.inter_op_num_threads = 1
        opts.intra_op_num_threads = 1
        providers = ['CPUExecutionProvider']
        self.session = onnxruntime.InferenceSession(
            model_path, providers=providers, sess_options=opts
        )
        self.reset_states()

    def reset_states(self, batch_size=1):
        self._state = np.zeros((2, batch_size, 128), dtype=np.float32)
        self._context = np.array([], dtype=np.float32)
        self._last_sr = 0
        self._last_batch_size = 0

    def __call__(self, chunk, sr):
        # chunk: 1D numpy float32 array
        if chunk.ndim == 1:
            chunk = chunk[np.newaxis, :]  # add batch dim

        num_samples = 512 if sr == 16000 else 256
        if chunk.shape[-1] != num_samples:
            raise ValueError(f"Expected {num_samples} samples, got {chunk.shape[-1]}")

        batch_size = chunk.shape[0]
        context_size = 64 if sr == 16000 else 32

        if not self._last_batch_size:
            self.reset_states(batch_size)
        if self._last_sr and self._last_sr != sr:
            self.reset_states(batch_size)
        if self._last_batch_size and self._last_batch_size != batch_size:
            self.reset_states(batch_size)

        if self._context.size == 0:
            self._context = np.zeros((batch_size, context_size), dtype=np.float32)

        x = np.concatenate([self._context, chunk], axis=1)
        ort_inputs = {
            'input': x.astype(np.float32),
            'state': self._state.astype(np.float32),
            'sr': np.array(sr, dtype=np.int64),
        }
        ort_outs = self.session.run(None, ort_inputs)
        out, state = ort_outs

        self._state = state
        self._context = x[:, -context_size:]
        self._last_sr = sr
        self._last_batch_size = batch_size

        return float(out.flat[0])
