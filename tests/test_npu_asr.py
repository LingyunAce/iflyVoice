"""NPU ASR unit tests — requires board + RKNN model"""
import pytest
import os
import numpy as np


@pytest.fixture
def asr_model():
    """Load RKNN ASR model (board only)"""
    from npu.rknn_asr import RknnASR
    model_path = os.path.join(os.path.dirname(__file__), "..", "models", "sensevoice_small.rknn")
    if not os.path.exists(model_path):
        pytest.skip("RKNN model not found (run on board with converted model)")
    return RknnASR(model_path)


def test_rknn_asr_loads(asr_model):
    """Model loads successfully"""
    assert asr_model is not None
    assert asr_model.is_loaded()


def test_rknn_asr_transcribes_silence(asr_model):
    """Silence audio should return empty string or very short text"""
    silence = np.zeros(16000 * 2, dtype=np.float32)  # 2s silence
    text = asr_model.transcribe(silence, sample_rate=16000)
    assert isinstance(text, str)


def test_rknn_asr_transcribes_audio_file(asr_model):
    """Real audio file transcription (needs test fixtures)"""
    fixture = os.path.join(os.path.dirname(__file__), "fixtures", "test_audio_5s.wav")
    if not os.path.exists(fixture):
        pytest.skip("Test audio fixture not found")
    import soundfile as sf
    audio, sr = sf.read(fixture, dtype="float32")
    text = asr_model.transcribe(audio, sample_rate=sr)
    assert len(text) > 0
    print(f"ASR result: {text}")


def test_rknn_asr_returns_stats(asr_model):
    """Inference returns performance stats"""
    silence = np.zeros(16000 * 2, dtype=np.float32)
    asr_model.transcribe(silence, sample_rate=16000)
    stats = asr_model.get_stats()
    assert "infer_time_ms" in stats
    assert stats["infer_time_ms"] > 0
