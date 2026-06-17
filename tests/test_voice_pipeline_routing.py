"""Verify voice_pipeline.py no longer directly calls deleted /ddcci/* HTTP endpoints"""
import inspect


def test_voice_pipeline_no_ddcci_http_calls():
    """voice_pipeline.py source should not contain /ddcci/ HTTP paths"""
    import voice_pipeline
    src = inspect.getsource(voice_pipeline)
    assert "/ddcci/" not in src, "voice_pipeline still contains /ddcci/ paths (deleted)"
    assert "taskkill" not in src, "voice_pipeline still contains taskkill (Windows)"


def test_voice_pipeline_uses_dispatcher():
    """voice_pipeline should have executor attribute (dispatcher)"""
    import voice_pipeline
    src = inspect.getsource(voice_pipeline.VoicePipeline)
    assert "self.executor" in src


def test_voice_pipeline_no_http_helpers():
    """voice_pipeline should not have dead _http_get_json/_http_post_json methods"""
    import voice_pipeline
    src = inspect.getsource(voice_pipeline.VoicePipeline)
    assert "_http_get_json" not in src, "voice_pipeline still has _http_get_json (dead code)"
    assert "_http_post_json" not in src, "voice_pipeline still has _http_post_json (dead code)"


def test_voice_pipeline_no_app_manager_imports():
    """voice_pipeline._execute_display_control should not import app_manager directly"""
    import voice_pipeline
    src = inspect.getsource(voice_pipeline.VoicePipeline._execute_display_control)
    assert "app_manager" not in src, "_execute_display_control still imports app_manager directly"
