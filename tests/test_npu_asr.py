"""NPU ASR unit tests — supports RKNN NPU and ONNX Runtime CPU backends"""
import pytest
import os
import numpy as np


@pytest.fixture
def asr_model():
    """Load ASR model — try RKNN first, then ONNX"""
    from npu.rknn_asr import RknnASR
    models_dir = os.path.join(os.path.dirname(__file__), "..", "models")

    # 优先 .rknn（板子 NPU）
    rknn_path = os.path.join(models_dir, "sensevoice_small.rknn")
    onnx_path = os.path.join(models_dir, "sensevoice_small.onnx")

    if os.path.exists(rknn_path):
        model = RknnASR(rknn_path)
        if model.is_loaded():
            return model

    if os.path.exists(onnx_path):
        model = RknnASR(onnx_path)
        if model.is_loaded():
            return model

    pytest.skip("No ASR model found (need sensevoice_small.rknn or .onnx in models/)")


def test_asr_loads(asr_model):
    """Model loads successfully"""
    assert asr_model is not None
    assert asr_model.is_loaded()
    assert asr_model.get_backend() in ("rknn", "onnx")


def test_asr_transcribes_silence(asr_model):
    """Silence audio should return string (may be empty or noise)"""
    silence = np.zeros(16000 * 2, dtype=np.float32)  # 2s silence
    text = asr_model.transcribe(silence, sample_rate=16000)
    assert isinstance(text, str)


def test_asr_transcribes_audio_file(asr_model):
    """Real audio file transcription (needs test fixtures)"""
    fixture = os.path.join(os.path.dirname(__file__), "fixtures", "test_audio_5s.wav")
    if not os.path.exists(fixture):
        pytest.skip("Test audio fixture not found")
    import soundfile as sf
    audio, sr = sf.read(fixture, dtype="float32")
    text = asr_model.transcribe(audio, sample_rate=sr)
    assert len(text) > 0
    print(f"ASR result: {text}")


def test_asr_returns_stats(asr_model):
    """Inference returns performance stats"""
    silence = np.zeros(16000 * 2, dtype=np.float32)
    asr_model.transcribe(silence, sample_rate=16000)
    stats = asr_model.get_stats()
    assert "infer_time_ms" in stats
    assert stats["infer_time_ms"] > 0
    assert "backend" in stats
    assert stats["backend"] in ("rknn", "onnx")


def test_asr_backend_info(asr_model):
    """Model reports which backend it uses"""
    backend = asr_model.get_backend()
    assert backend in ("rknn", "onnx")
    print(f"Backend: {backend}")
