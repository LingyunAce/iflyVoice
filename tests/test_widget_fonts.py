def test_widget_module_imports():
    """widget.py should import (PySide6 available)"""
    try:
        import widget
        assert hasattr(widget, "_preferred_font")
    except ImportError as e:
        import pytest
        pytest.skip(f"PySide6 not available: {e}")


def test_preferred_font_returns_qfont():
    """_preferred_font should return a QFont object"""
    try:
        from PySide6.QtWidgets import QApplication
        from PySide6.QtGui import QFont
        # QFontDatabase.families() 需要 QApplication 实例
        app = QApplication.instance() or QApplication([])
        from widget import _preferred_font
        f = _preferred_font()
        assert isinstance(f, QFont)
    except ImportError:
        import pytest
        pytest.skip("PySide6 not available")
