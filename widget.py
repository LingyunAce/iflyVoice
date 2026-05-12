#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Voice AI Widget — 圆形悬浮球变形为胶囊聊天面板 + 内嵌 HTTP 服务
"""
import sys, os, json, time, threading, tempfile, uuid, wave
import http.client
import numpy as np
import sounddevice as sd
from urllib.request import urlopen, Request
from urllib.error import HTTPError

from PySide6.QtWidgets import QApplication, QWidget, QVBoxLayout, QHBoxLayout
from PySide6.QtWidgets import QLabel, QLineEdit, QPushButton, QScrollArea
from PySide6.QtWidgets import QSizePolicy, QStackedWidget, QTextEdit, QFrame
from PySide6.QtWidgets import QGraphicsOpacityEffect
from PySide6.QtCore import (Qt, QPropertyAnimation, QParallelAnimationGroup,
                             QUrl, QSize, Property, QEasingCurve, QTimer,
                             QSequentialAnimationGroup, QPoint, QRectF, QRect, Signal,
                             QMetaObject, Q_ARG, Slot)
from PySide6.QtGui import (QPainter, QColor, QBrush, QPen, QFont, QPixmap,
                            QIcon, QCursor, QPainterPath, QFontMetrics, QTextOption)
from PySide6.QtMultimedia import QMediaPlayer, QAudioOutput

SERVER_URL = "http://127.0.0.1:18766"
OLLAMA_URL = SERVER_URL + "/ollama"
SENSEVOICE_URL = SERVER_URL + "/sensevoice/transcribe"
TTS_URL = SERVER_URL + "/v1/audio/speech"


def _log(msg):
    print(f"[VoiceAI] {msg}", file=sys.stderr, flush=True)

# ── 文件日志 ─────────────────────────────────────────────────
_log_path = os.path.join(os.path.dirname(__file__), "widget.log")
_log_file = open(_log_path, "a", encoding="utf-8")

def _flog(msg):
    ts = time.strftime("%H:%M:%S")
    ms = int(time.time() * 1000) % 1000
    line = f"{ts}.{ms:03d} {msg}"
    _log_file.write(line + "\n")
    _log_file.flush()
    print(f"[VoiceAI] {line}", file=sys.stderr, flush=True)


# ═══════════════════════════════════════════════════════════════════
#  Icon Drawing
# ═══════════════════════════════════════════════════════════════════

def draw_close_icon(size=18):
    pix = QPixmap(size, size)
    pix.fill(Qt.transparent)
    p = QPainter(pix)
    p.setRenderHint(QPainter.Antialiasing)
    p.setPen(QPen(QColor("#aaa"), 2))
    p.drawLine(3, 3, size - 3, size - 3)
    p.drawLine(size - 3, 3, 3, size - 3)
    p.end()
    return pix


# ═══════════════════════════════════════════════════════════════════
#  ChatBubble — QLabel 气泡
#   短文本：wordWrap=False，不设任何宽度约束 → Qt sizeHint 精确返回文本宽
#   长文本：wordWrap=True  + setFixedWidth(240) → 自动换行
#  关键：setWordWrap(True) 时 Qt 的 sizeHint 返回"理想段落宽度"（偏窄），
#        所以绝对不能在 wrap 模式下靠 sizeHint 决定宽度。
#        但 wrap=False 时 sizeHint = 文本实际宽度，完全准确。
# ═══════════════════════════════════════════════════════════════════
class ChatBubble(QLabel):
    MAX_BUBBLE_W = 240   # 长文本换行时气泡宽度（含 padding）
    PAD_H = 24           # padding 左 12 + 右 12

    def __init__(self, text, is_user=False, parent=None):
        super().__init__(parent)
        self.is_user = is_user
        self.full_text = ""

        self.setTextFormat(Qt.PlainText)
        self.setFont(QFont("Microsoft YaHei UI", 10))
        self.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Preferred)

        if is_user:
            self.setStyleSheet(
                "QLabel { background:#95EC69; color:#000000; "
                "border-radius:10px; padding:8px 12px; }"
            )
        else:
            self.setStyleSheet(
                "QLabel { background:#ffffff; color:#000000; "
                "border-radius:10px; padding:8px 12px; }"
            )

        self._set_content(text or "")

    def _natural_width(self, text):
        """估算文本自然宽度（最长行宽 + padding + 安全余量）"""
        fm = QFontMetrics(self.font())
        lines = text.split('\n') if text else ['']
        max_w = 0
        for line in lines:
            w = fm.horizontalAdvance(line) if hasattr(fm, 'horizontalAdvance') \
                else fm.width(line)
            if w > max_w:
                max_w = w
        return max_w + self.PAD_H

    def _set_content(self, text):
        """设置文本并动态切换 wordWrap 模式"""
        self.full_text = text
        super().setText(text)
        natural = self._natural_width(text)
        if natural <= self.MAX_BUBBLE_W:
            # 短文本：关闭换行，不设任何宽度约束
            # setWordWrap(False) 时 sizeHint = 文本实际宽度，完全精确
            # QSizePolicy.Maximum 保证不会被布局拉伸
            self.setWordWrap(False)
            # 清除可能残留的固定宽度
            self.setMinimumWidth(0)
            self.setMaximumWidth(16777215)
        else:
            # 长文本：开启换行，固定宽度
            self.setWordWrap(True)
            self.setFixedWidth(self.MAX_BUBBLE_W)

    def setText(self, text):
        self._set_content(text or "")


# ═══════════════════════════════════════════════════════════════════
#  Circle Button (收起态)
# ═══════════════════════════════════════════════════════════════════
class CircleButton(QWidget):
    clicked = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(56, 56)
        self._hovered = False
        self._pressed = False
        self._recording = False
        self._rec_phase = 0
        self._rec_timer = QTimer(self)
        self._rec_timer.timeout.connect(self._toggle_rec)
        self.setCursor(QCursor(Qt.PointingHandCursor))

    def set_recording(self, on):
        self._recording = on
        if on:
            self._rec_timer.start(400)
        else:
            self._rec_timer.stop()
            self._rec_phase = 0
        self.update()

    def _toggle_rec(self):
        self._rec_phase = (self._rec_phase + 1) % 2
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setPen(Qt.NoPen)
        s = self.width()

        if self._recording:
            bg = QColor(255, 107, 107, 230).lighter(115) if self._rec_phase else QColor(255, 107, 107, 230)
        elif self._pressed:
            bg = QColor("#92400E")
        elif self._hovered:
            bg = QColor("#B85C00")
        else:
            bg = QColor("#D97706")

        p.setBrush(QBrush(bg))
        p.drawEllipse(0, 0, s, s)

        if self._recording:
            box = s * 0.28
            cx, cy = s / 2, s / 2
            p.setPen(QPen(Qt.white, 2.5))
            p.setBrush(Qt.NoBrush)
            p.drawRect(int(cx - box), int(cy - box), int(box * 2), int(box * 2))
        else:
            # 矢量绘制 "C" 字母，边缘始终平滑
            p.setPen(QPen(Qt.white, max(2, s // 10)))
            p.setBrush(Qt.NoBrush)
            p.setFont(QFont("Arial", max(10, int(s * 0.48)), QFont.Bold))
            p.drawText(0, 0, s, s, Qt.AlignCenter, "C")
        p.end()

    def enterEvent(self, event):
        self._hovered = True; self.update()

    def leaveEvent(self, event):
        self._hovered = False; self.update()

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._pressed = True
            self._drag_start = event.globalPosition().toPoint()
            # 找到顶层 MainWidget
            w = self.window()
            self._drag_win_origin = w.pos()
            self.update()
            event.accept()

    def mouseMoveEvent(self, event):
        if self._pressed:
            delta = event.globalPosition().toPoint() - self._drag_start
            self.window().move(self._drag_win_origin + delta)
            event.accept()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton and self._pressed:
            delta = event.globalPosition().toPoint() - self._drag_start
            self._pressed = False
            self.update()
            if abs(delta.x()) + abs(delta.y()) < 6:
                self.clicked.emit()
            event.accept()


# ═══════════════════════════════════════════════════════════════════
#  Chat Panel (展开态)
# ═══════════════════════════════════════════════════════════════════
class ChatPanel(QWidget):
    def __init__(self, main_widget, parent=None):
        super().__init__(parent)
        self._main = main_widget
        self.setFixedWidth(300)
        self.setMinimumHeight(400)
        self.setMaximumHeight(520)
        self.setStyleSheet("""
            ChatPanel {
                background: #2b3441;
                border: 1px solid #3a4555;
                border-radius: 18px;
            }
            QScrollArea { background:transparent; border:none; }
            QPushButton {
                background:#4ECDC4; color:white; border:none; border-radius:8px;
                padding:6px 12px; font-family:"Microsoft YaHei UI";
            }
            QPushButton:hover { background:#5fd9d2; }
            QPushButton:pressed { background:#3dbdb5; }
            QLineEdit {
                background:#1a2029; color:white; border:1px solid #3a4555;
                border-radius:8px; padding:6px 10px; font-family:"Microsoft YaHei UI";
            }
            QLineEdit:focus { border:1px solid #4ECDC4; }
        """)
        self.setAttribute(Qt.WA_StyledBackground)

        # 透明度效果（用于展开/收起淡入淡出动画）
        self._opacity_effect = QGraphicsOpacityEffect(self)
        self._opacity_effect.setOpacity(1.0)
        self.setGraphicsEffect(self._opacity_effect)

        ml = QVBoxLayout(self)
        ml.setContentsMargins(0, 0, 0, 0)
        ml.setSpacing(0)

        # 标题栏
        header = QWidget()
        header.setFixedHeight(44)
        header.setStyleSheet("background:#1a2029; border:none;")
        hl = QHBoxLayout(header)
        hl.setContentsMargins(14, 0, 8, 0)

        dot = QLabel("●")
        dot.setStyleSheet("color:#D97706; font-size:14px; background:transparent;")
        dot.setFixedWidth(18)

        title = QLabel("AI 助手")
        title.setFont(QFont("Microsoft YaHei UI", 11, QFont.Bold))
        title.setStyleSheet("color:#e0e0e0; background:transparent;")

        spacer = QWidget()
        spacer.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)

        self.status_lbl = QLabel("")
        self.status_lbl.setFont(QFont("Microsoft YaHei UI", 9))
        self.status_lbl.setStyleSheet("color:#888; background:transparent;")

        close_btn = QPushButton()
        close_btn.setIcon(QIcon(draw_close_icon(14)))
        close_btn.setFixedSize(22, 22)
        close_btn.setStyleSheet("background:transparent; border:none;")
        close_btn.clicked.connect(lambda: self._main._collapse())

        hl.addWidget(dot)
        hl.addWidget(title)
        hl.addWidget(spacer)
        hl.addWidget(self.status_lbl)
        hl.addWidget(close_btn)
        ml.addWidget(header)

        # 消息区
        sa = QScrollArea()
        sa.setWidgetResizable(True)
        sa.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        sa.setStyleSheet("QScrollArea { background:transparent; border:none; }")
        self.msg_container = QWidget()
        self.msg_container.setStyleSheet("background:transparent;")
        vl = QVBoxLayout(self.msg_container)
        vl.setContentsMargins(8, 10, 8, 4)
        vl.setSpacing(6)
        vl.setAlignment(Qt.AlignTop)  # 内容靠顶，不居中分布
        sa.setWidget(self.msg_container)
        self.scroll_area = sa
        ml.addWidget(sa, 1)

        # 输入区
        iw = QWidget()
        iw.setStyleSheet("background:#1a2029; border:none;")
        il = QVBoxLayout(iw)
        il.setContentsMargins(8, 6, 8, 8)
        il.setSpacing(6)

        row1 = QHBoxLayout()
        row1.setSpacing(6)
        self.input_box = QLineEdit()
        self.input_box.setPlaceholderText("输入消息...")
        self.input_box.setFixedHeight(32)
        self.input_box.returnPressed.connect(self._on_send)
        send_btn = QPushButton("发送")
        send_btn.setFixedSize(52, 32)
        send_btn.clicked.connect(self._on_send)
        row1.addWidget(self.input_box, 1)
        row1.addWidget(send_btn)

        row2 = QHBoxLayout()
        row2.setSpacing(6)
        self.mic_btn = QPushButton("🎤 语音")
        self.mic_btn.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        self.mic_btn.clicked.connect(lambda: self._main._toggle_recording())
        tts_btn = QPushButton("🔊 朗读")
        tts_btn.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        row2.addWidget(self.mic_btn, 1)
        row2.addWidget(tts_btn, 1)

        il.addLayout(row1)
        il.addLayout(row2)
        ml.addWidget(iw)

    def _on_send(self):
        text = self.input_box.text().strip()
        _log(f"[SEND] text='{text}'")
        if not text:
            return
        self.input_box.clear()
        self._main._on_user_message(text)

    def add_bubble(self, text, is_user):
        b = ChatBubble(text, is_user, self.msg_container)

        # 每个气泡一个独立行，行满宽，内部用 stretch 推气泡到左/右
        row = QWidget(self.msg_container)
        row_l = QHBoxLayout(row)
        row_l.setContentsMargins(0, 0, 0, 0)
        row_l.setSpacing(0)

        if is_user:
            row_l.addStretch(1)       # 左侧撑 → 气泡挤到右边
            row_l.addWidget(b)
        else:
            row_l.addWidget(b)        # 气泡在左边
            row_l.addStretch(1)       # 右侧撑 → 气泡保持左对齐

        # row 必须满宽让 stretch 生效，高度固定为气泡高度
        row.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)

        layout = self.msg_container.layout()
        # AlignTop：所有行靠顶部排列，不留上面空白
        layout.addWidget(row, 0, Qt.AlignTop)
        QTimer.singleShot(50, self._scroll_to_bottom)
        return b

    def _scroll_to_bottom(self):
        sb = self.scroll_area.verticalScrollBar()
        sb.setValue(sb.maximum())


# ═══════════════════════════════════════════════════════════════════
#  Main Widget
# ═══════════════════════════════════════════════════════════════════
class MainWidget(QWidget):
    BUBBLE_DIA = 56
    PILL_W, PILL_H = 310, 520
    ANIM_MS = 350

    # 跨线程信号
    sig_stream = Signal(str)
    sig_done = Signal(str)
    sig_error = Signal(str)
    sig_status = Signal(str)      # 跨线程更新状态文字
    sig_transcribe = Signal(str)
    sig_transcribe_err = Signal(str)
    sig_tts_play = Signal(str)

    def __init__(self):
        super().__init__()
        self._expanded = False
        self._recording = False
        self._chat_cancelled = False
        self._ai_bubble = None
        self._audio_recorder = None
        self._audio_session = None
        self._audio_input = None
        self._stream_buf = ""
        self._stream_dirty = False
        self._flush_timer = QTimer(self)
        self._flush_timer.setInterval(150)
        self._flush_timer.timeout.connect(self._flush_stream)

        # 等待进度计时器：显示"思考中... (Ns)"，缓解首次加载卡死感
        self._wait_timer = QTimer(self)
        self._wait_timer.setInterval(3000)
        self._wait_timer.timeout.connect(self._tick_wait)
        self._wait_seconds = 0

        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setMouseTracking(True)

        # 使用 QStackedWidget 切换圆形/面板
        self._stack = QStackedWidget(self)
        self._stack.setMouseTracking(True)

        # 页面 0：圆形按钮
        self._circle = CircleButton()
        self._circle.clicked.connect(self._expand)
        self._stack.addWidget(self._circle)

        # 页面 1：聊天面板
        self._panel = ChatPanel(self)
        self._panel.hide()
        self._stack.addWidget(self._panel)

        # 截图标签（展开/收起动画用，浮在最上层）
        self._anim_label = QLabel(self)
        self._anim_label.hide()
        self._anim_label.setAttribute(Qt.WA_TransparentForMouseEvents)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._stack)

        # 连接跨线程信号
        self.sig_stream.connect(self._on_stream_token)
        self.sig_done.connect(self._on_ai_done)
        self.sig_error.connect(self._on_ai_error)
        self.sig_status.connect(lambda s: self._panel.status_lbl.setText(s))
        self.sig_tts_play.connect(self._play_tts)
        self.sig_transcribe.connect(self._on_transcribe_done)
        self.sig_transcribe_err.connect(self._on_transcribe_error)

        # 初始：只显示圆形
        self.setFixedSize(self.BUBBLE_DIA, self.BUBBLE_DIA)
        self._move_to_corner()
        self.show()

    def _move_to_corner(self):
        screen = QApplication.primaryScreen()
        if screen:
            geo = screen.geometry()
            self.move(geo.right() - self.width() - 20, geo.bottom() - self.height() - 20)

    # ── 展开 / 收起动画 ──────────────────────────────────────
    def _grab_panel(self):
        """截取面板当前画面为 QPixmap"""
        pixmap = QPixmap(self._panel.size())
        pixmap.fill(Qt.transparent)
        self._panel.render(pixmap)
        return pixmap

    def _expand(self):
        if self._expanded:
            return
        self._expanded = True

        start_pos = self.pos()
        self._ball_pos = start_pos
        target_x = max(0, start_pos.x() + self.BUBBLE_DIA - self.PILL_W)
        target_y = max(0, start_pos.y() + self.BUBBLE_DIA - self.PILL_H)

        # 先把窗口扩展到最终大小，面板渲染一帧后截图
        self.setMinimumSize(self.PILL_W, self.PILL_H)
        self.setMaximumSize(self.PILL_W, self.PILL_H)
        self.move(target_x, target_y)
        self._panel.show()
        self._stack.setCurrentIndex(1)
        QApplication.processEvents()

        pixmap = self._grab_panel()

        # 隐藏真实面板，显示截图
        self._panel.hide()
        self._anim_label.setPixmap(pixmap)
        self._anim_label.setGeometry(0, 0, self.PILL_W, self.PILL_H)
        self._anim_label.show()

        # 动画：截图从球大小缩放到面板大小（在窗口内）
        self._anim_label.setGeometry(
            self.PILL_W - self.BUBBLE_DIA,  # 右下角对齐
            self.PILL_H - self.BUBBLE_DIA,
            self.BUBBLE_DIA, self.BUBBLE_DIA
        )

        end_geo = QRect(0, 0, self.PILL_W, self.PILL_H)

        anim = QPropertyAnimation(self._anim_label, b"geometry")
        anim.setDuration(self.ANIM_MS)
        anim.setEndValue(end_geo)
        anim.setEasingCurve(QEasingCurve.OutCubic)
        self._expand_anim = anim

        anim.finished.connect(self._on_expand_done)
        anim.start()

    def _on_expand_done(self):
        self._anim_label.hide()
        self._anim_label.clear()
        self._panel._opacity_effect.setOpacity(1.0)
        self._panel.show()
        self._panel.input_box.setFocus()

    def _collapse(self):
        if not self._expanded:
            return

        target_pos = getattr(self, '_ball_pos', self.pos())

        # 截取当前面板画面
        pixmap = self._grab_panel()
        self._panel.hide()
        self._anim_label.setPixmap(pixmap)
        self._anim_label.setGeometry(0, 0, self.PILL_W, self.PILL_H)
        self._anim_label.show()

        # 动画：截图从面板大小缩放到球大小（缩到右下角）
        end_geo = QRect(
            self.PILL_W - self.BUBBLE_DIA,
            self.PILL_H - self.BUBBLE_DIA,
            self.BUBBLE_DIA, self.BUBBLE_DIA
        )

        anim = QPropertyAnimation(self._anim_label, b"geometry")
        anim.setDuration(self.ANIM_MS)
        anim.setEndValue(end_geo)
        anim.setEasingCurve(QEasingCurve.InCubic)
        self._collapse_anim = anim

        anim.finished.connect(self._on_collapse_done)
        anim.start()

    def _on_collapse_done(self):
        self._expanded = False
        self._anim_label.hide()
        self._anim_label.clear()
        self._panel.hide()
        self._panel._opacity_effect.setOpacity(1.0)
        self._stack.setCurrentIndex(0)
        self.setFixedSize(self.BUBBLE_DIA, self.BUBBLE_DIA)
        self.setMinimumSize(0, 0)
        self.setMaximumSize(16777215, 16777215)
        if hasattr(self, '_ball_pos'):
            self.move(self._ball_pos)

    # ── 聊天 ──────────────────────────────────────────────────
    def _on_user_message(self, text):
        self._panel.add_bubble(text, True)
        self._chat_with_ai(text)

    def _chat_with_ai(self, text):
        self._panel.status_lbl.setText("连接 AI 服务...")
        self._ai_bubble = None
        self._wait_seconds = 0
        self._wait_timer.start()
        self._chat_cancelled = False
        threading.Thread(target=self._do_chat, args=(text,), daemon=True).start()

    def _tick_wait(self):
        self._wait_seconds += 3
        self._panel.status_lbl.setText(f"思考中... ({self._wait_seconds}s)")

    def _do_chat(self, text):
        _log(f"[CHAT] 开始请求")
        try:
            # 1. 预检：快速检测 ollama 是否可达（3 秒超时，快速失败）
            try:
                pre = Request("http://127.0.0.1:18766/ollama/api/tags",
                              headers={"Content-Type": "application/json"})
                urlopen(pre, timeout=3).close()
                _log("[CHAT] 预检通过")
            except Exception as e:
                _log(f"[CHAT] 预检失败: {e}")
                self.sig_error.emit(f"AI 服务不可达: {e}")
                return

            self.sig_status.emit("模型加载中...")

            # 2. 正式请求：使用 urllib（比 http.client 对 GIL 更友好）
            payload = json.dumps({
                "model": "qwen3-vl:4b",
                "messages": [{"role": "user", "content": text}],
                "stream": True
            }).encode()

            req = Request("http://127.0.0.1:18766/ollama/api/chat",
                          data=payload,
                          headers={"Content-Type": "application/json"},
                          method="POST")
            resp = urlopen(req, timeout=90)
            _log(f"[CHAT] 响应 status={resp.status}")

            full = ""
            buf = b""
            token_count = 0
            while not self._chat_cancelled:
                chunk = resp.read(4096)
                if not chunk:
                    break
                buf += chunk
                while b"\n" in buf:
                    line_bytes, buf = buf.split(b"\n", 1)
                    line = line_bytes.decode("utf-8", errors="replace").strip()
                    if not line or line == "done":
                        continue
                    if line.startswith("data:"):
                        line = line[5:].strip()
                    try:
                        obj = json.loads(line)
                        token = (obj.get("message", {}) or {}).get("content", "") or obj.get("content", "")
                        if token:
                            full += token
                            token_count += 1
                            if token_count % 20 == 0:
                                _flog(f"[CHAT] tokens={token_count} len={len(full)}")
                            # 每 5 个 token emit 一次，减少主线程信号队列压力
                            if token_count % 5 == 0 or token_count == 1:
                                self.sig_stream.emit(full)
                    except json.JSONDecodeError:
                        continue

            resp.close()
            if self._chat_cancelled:
                _log(f"[CHAT] 已取消")
                self.sig_error.emit("已取消")
            else:
                _log(f"[CHAT] 完成 tokens={token_count}")
                self.sig_done.emit(full)

        except Exception as e:
            _log(f"[CHAT] 错误: {e}")
            self.sig_error.emit(str(e))

    def _on_stream_token(self, full):
        self._stream_buf = full
        self._stream_dirty = True
        if self._ai_bubble is None:
            # 首个 token：立即创建气泡，同时启动后续刷新 timer
            self._flush_stream()
        if not self._flush_timer.isActive():
            self._flush_timer.start()

    def _flush_stream(self):
        if not self._stream_dirty:
            return
        self._stream_dirty = False
        if self._wait_timer.isActive():
            self._wait_timer.stop()
        full = self._stream_buf
        self._panel.status_lbl.setText("")
        if self._ai_bubble is None:
            self._ai_bubble = self._panel.add_bubble(full, False)
        else:
            self._ai_bubble.setText(full)
            self._panel._scroll_to_bottom()

    def _on_ai_done(self, full):
        _flog(f"[DONE] len={len(full)}")
        self._wait_timer.stop()
        self._flush_timer.stop()
        # 强制用最终文本更新气泡（忽略 dirty 标记）
        if self._ai_bubble and full:
            self._ai_bubble.setText(full)
            self._panel._scroll_to_bottom()
        self._panel.status_lbl.setText("")
        self._ai_bubble = None
        _flog(f"[DONE] 完成")
        if full and len(full) < 600:
            self._speak(full)

    def _on_ai_error(self, err):
        self._wait_timer.stop()
        self._flush_timer.stop()
        self._panel.status_lbl.setText("")
        self._panel.add_bubble(f"[错误] {err}", False)

    def _speak(self, text):
        threading.Thread(target=self._do_speak, args=(text,), daemon=True).start()

    def _do_speak(self, text):
        try:
            payload = json.dumps({
                "model": "CosyVoice2-0.5B",
                "input": text,
                "response_format": "mp3",
            }).encode()

            req = Request(TTS_URL, data=payload,
                          headers={"Content-Type": "application/json", "Accept": "audio/mpeg"},
                          method="POST")

            with urlopen(req, timeout=15) as resp:
                audio = resp.read()

            mp3 = os.path.join(tempfile.gettempdir(), f"tts_{uuid.uuid4().hex}.mp3")
            with open(mp3, "wb") as f:
                f.write(audio)

            # QMediaPlayer 必须在主线程创建，用 signal 触发
            self.sig_tts_play.emit(mp3)

        except Exception as e:
            _flog(f"[TTS] 错误: {e}")

    def _play_tts(self, mp3):
        try:
            player = QMediaPlayer()
            out = QAudioOutput()
            player.setAudioOutput(out)
            player.setSource(QUrl.fromLocalFile(mp3))
            player.play()

            def cleanup():
                try:
                    os.unlink(mp3)
                except Exception:
                    pass
            player.playbackChanged.connect(cleanup)
        except Exception as e:
            _flog(f"[TTS] 播放错误: {e}")

    # ── 录音（QMediaCaptureSession + QMediaRecorder）──
    def _toggle_recording(self):
        if self._recording:
            self._stop_recording()
        else:
            self._start_recording()

    def _start_recording(self):
        _log("[REC] 开始录音")
        self._recording = True
        self._circle.set_recording(True)
        self._panel.mic_btn.setText("■ 停止")
        self._panel.status_lbl.setText("正在录音...")

        try:
            self._rec_chunks = []
            self._rec_stream = sd.InputStream(
                samplerate=16000, channels=1, dtype='int16',
                callback=self._audio_callback
            )
            self._rec_stream.start()
            _log("[REC] 录音中 (sounddevice)")

            QTimer.singleShot(30000, self._stop_recording)

        except Exception as e:
            _log(f"[REC] 录音失败: {e}")
            self._panel.status_lbl.setText(f"录音失败: {e}")
            self._recording = False
            self._circle.set_recording(False)
            self._panel.mic_btn.setText("🎤 语音")

    def _audio_callback(self, indata, frames, time_info, status):
        if self._recording:
            self._rec_chunks.append(indata.copy())

    def _stop_recording(self):
        if not self._recording:
            return
        _log("[REC] 停止录音")
        self._recording = False
        self._circle.set_recording(False)
        self._panel.mic_btn.setText("🎤 语音")
        self._panel.status_lbl.setText("识别中...")

        try:
            if self._rec_stream:
                self._rec_stream.stop()
                self._rec_stream.close()

            # 合并 PCM 录音块
            audio = np.concatenate(self._rec_chunks, axis=0)
            pcm_data = audio.tobytes()
            _log(f"[REC] PCM: {len(pcm_data)} bytes, {len(audio)} samples")

            # 通过 ffmpeg 转为 webm/opus（和浏览器 MediaRecorder 输出一致）
            self._rec_file = os.path.join(tempfile.gettempdir(), f"voice_{uuid.uuid4().hex}.webm")
            import subprocess
            proc = subprocess.run(
                ["ffmpeg", "-y", "-f", "s16le", "-ar", "16000", "-ac", "1",
                 "-i", "pipe:0", "-c:a", "libopus", "-b:a", "32k", self._rec_file],
                input=pcm_data, capture_output=True, timeout=15
            )
            if proc.returncode != 0:
                _log(f"[REC] ffmpeg 错误: {proc.stderr.decode('utf-8', errors='replace')[:200]}")
                self.sig_transcribe_err.emit("ffmpeg 转码失败")
                return

            _log(f"[REC] webm 已保存: {self._rec_file}")
            threading.Thread(target=self._transcribe, daemon=True).start()

        except Exception as e:
            _log(f"[REC] 停止失败: {e}")
            self._panel.status_lbl.setText(f"录音错误: {e}")

    def _transcribe(self):
        """上传 webm/opus 录音到 /sensevoice/transcribe（和 Web UI 一致）"""
        try:
            boundary = uuid.uuid4().hex
            with open(self._rec_file, "rb") as f:
                audio_data = f.read()

            body = b""
            body += f"--{boundary}\r\n".encode()
            body += b'Content-Disposition: form-data; name="file"; filename="recording.webm"\r\n'
            body += b"Content-Type: audio/webm\r\n\r\n"
            body += audio_data
            body += b"\r\n"
            body += f"--{boundary}--\r\n".encode()

            conn = http.client.HTTPConnection("127.0.0.1", 18766, timeout=30)
            conn.request("POST", "/sensevoice/transcribe", body=body,
                         headers={"Content-Type": f"multipart/form-data; boundary={boundary}"})
            resp = conn.getresponse()
            data = json.loads(resp.read().decode("utf-8"))
            conn.close()

            text = data.get("text", "") if data.get("success") else ""
            error = data.get("error", "")
            _log(f"[REC] 识别结果: text='{text}'")

            if text:
                self.sig_transcribe.emit(text)
            else:
                _log(f"[REC] 识别失败: {error[:100]}")
                self.sig_transcribe_err.emit(error or "无识别结果")

        except Exception as e:
            _log(f"[REC] 识别错误: {e}")
            self.sig_transcribe_err.emit(str(e))
        finally:
            try:
                os.unlink(self._rec_file)
            except:
                pass

    def _on_transcribe_done(self, text):
        self._panel.status_lbl.setText("")
        self._on_user_message(text)

    def _on_transcribe_error(self, err):
        self._panel.status_lbl.setText(f"识别失败: {err[:50]}")


# ═══════════════════════════════════════════════════════════════════
#  Main
# ═══════════════════════════════════════════════════════════════════
def run_server():
    import server
    server.main()


def main():
    t = threading.Thread(target=run_server, daemon=True)
    t.start()

    for i in range(30):
        try:
            urlopen(SERVER_URL + "/", timeout=1)
            _log("HTTP 服务就绪")
            break
        except Exception:
            time.sleep(0.5)
    else:
        _log("警告: HTTP 服务未能在 15 秒内就绪")

    app = QApplication(sys.argv)
    app.setApplicationName("VoiceAI")
    app.setQuitOnLastWindowClosed(False)

    w = MainWidget()
    app.aboutToQuit.connect(w.close)
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
