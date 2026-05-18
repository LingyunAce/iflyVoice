#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Voice AI Widget — 圆形悬浮球变形为胶囊聊天面板 + 内嵌 HTTP 服务
"""
import sys, os, json, time, threading, subprocess, re
from urllib.request import urlopen, Request
import sounddevice as sd

from PySide6.QtWidgets import QApplication, QWidget, QVBoxLayout, QHBoxLayout
from PySide6.QtWidgets import QLabel, QLineEdit, QPushButton, QScrollArea
from PySide6.QtWidgets import QSizePolicy, QStackedWidget
from PySide6.QtWidgets import QGraphicsOpacityEffect, QComboBox, QCheckBox
from PySide6.QtCore import (Qt, QPropertyAnimation, QParallelAnimationGroup,
                             QSize, QEasingCurve, QTimer,
                             QPoint, QRect, Signal)
from PySide6.QtGui import (QPainter, QColor, QBrush, QPen, QFont, QPixmap,
                            QIcon, QCursor, QFontMetrics)

SERVER_URL = "http://127.0.0.1:18766"

from voice_pipeline import parse_voice_command
from utils import _strip_md, _flog as _flog_shared, _log_path

OLLAMA_URL = SERVER_URL + "/ollama"
SENSEVOICE_URL = SERVER_URL + "/sensevoice/transcribe"
TTS_URL = SERVER_URL + "/v1/audio/speech"


def _log(msg):
    print(f"[VoiceAI] {msg}", file=sys.stderr, flush=True)

def _flog(msg):
    _flog_shared("[VoiceAI]", msg)


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


def _md_to_html(text):
    """将 markdown 转为 HTML，供气泡显示"""
    if not text:
        return ""
    import html as _html
    s = text
    # 代码块 ```...``` → <pre>
    def _code_block(m):
        code = _html.escape(m.group(1).strip())
        return f'<pre style="background:#f0f0f0;border-radius:4px;padding:6px;margin:4px 0;white-space:pre-wrap;font-size:9pt;">{code}</pre>'
    s = re.sub(r'```(\w*)\n?([\s\S]*?)```', _code_block, s)
    # 行内代码
    s = re.sub(r'`([^`\n]+)`', r'<code style="background:#f0f0f0;border-radius:3px;padding:1px 4px;font-size:9pt;">\1</code>', s)
    # 图片 → alt 文字
    s = re.sub(r'!\[([^\]]*)\]\([^)]*\)', r'\1', s)
    # 链接
    s = re.sub(r'\[([^\]]+)\]\(([^)]+)\)', r'<a href="\2" style="color:#2563eb;">\1</a>', s)
    # 标题
    s = re.sub(r'^#### (.+)$', r'<b style="font-size:10pt;">\1</b>', s, flags=re.MULTILINE)
    s = re.sub(r'^### (.+)$', r'<b style="font-size:10.5pt;">\1</b>', s, flags=re.MULTILINE)
    s = re.sub(r'^## (.+)$', r'<b style="font-size:11pt;">\1</b>', s, flags=re.MULTILINE)
    s = re.sub(r'^# (.+)$', r'<b style="font-size:11.5pt;">\1</b>', s, flags=re.MULTILINE)
    # 加粗
    s = re.sub(r'\*\*(.+?)\*\*', r'<b>\1</b>', s)
    s = re.sub(r'__(.+?)__', r'<b>\1</b>', s)
    # 斜体
    s = re.sub(r'\*(.+?)\*', r'<i>\1</i>', s)
    s = re.sub(r'(?<!\w)_(.+?)_(?!\w)', r'<i>\1</i>', s)
    # 删除线
    s = re.sub(r'~~(.+?)~~', r'<s>\1</s>', s)
    # 引用
    s = re.sub(r'^>\s?(.+)$', r'<span style="color:#888;border-left:3px solid #ccc;padding-left:6px;">\1</span>', s, flags=re.MULTILINE)
    # 水平线
    s = re.sub(r'^[-*_]{3,}\s*$', '<hr style="border:none;border-top:1px solid #ddd;margin:6px 0;">', s, flags=re.MULTILINE)
    # 无序列表
    s = re.sub(r'^[\s]*[-*+]\s+(.+)$', r'&bull; \1', s, flags=re.MULTILINE)
    # 有序列表保持数字
    s = re.sub(r'^[\s]*(\d+)\.\s+(.+)$', r'\1. \2', s, flags=re.MULTILINE)
    # 表格行 → 简化
    s = re.sub(r'^\|?[\s:]*-+[\s:]*(\|[\s:]*-+[\s:]*)*\|?\s*$', '', s, flags=re.MULTILINE)
    s = re.sub(r'^\|(.+)\|$', lambda m: m.group(1).replace('|', ' | '), s, flags=re.MULTILINE)
    # HTML 标签保留（已处理的）
    # 换行
    s = s.replace('\n', '<br>')
    # 多余 <br> 压缩
    s = re.sub(r'(<br>){3,}', '<br><br>', s)
    return s


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
        if self.is_user:
            # 用户消息：纯文本
            self.setTextFormat(Qt.PlainText)
            super().setText(text)
            natural = self._natural_width(text)
            if natural <= self.MAX_BUBBLE_W:
                self.setWordWrap(False)
                self.setMinimumWidth(0)
                self.setMaximumWidth(16777215)
            else:
                self.setWordWrap(True)
                self.setFixedWidth(self.MAX_BUBBLE_W)
        else:
            # AI 消息：渲染 markdown → HTML
            self.setTextFormat(Qt.RichText)
            html = _md_to_html(text)
            super().setText(html)
            natural = self._natural_width(text)
            if natural <= self.MAX_BUBBLE_W:
                self.setWordWrap(False)
                self.setMinimumWidth(0)
                self.setMaximumWidth(16777215)
            else:
                self.setWordWrap(True)
                self.setFixedWidth(self.MAX_BUBBLE_W)

    def setText(self, text):
        self._set_content(text or "")


# ═══════════════════════════════════════════════════════════════════
#  Circle Button (收起态)
# ═══════════════════════════════════════════════════════════════════
class CircleButton(QWidget):
    clicked = Signal()
    right_clicked = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(56, 56)
        self._hovered = False
        self._pressed = False
        self._anim_state = "idle"
        self._anim_phase = 0
        self._anim_timer = QTimer(self)
        self._anim_timer.timeout.connect(self._tick_anim)
        self.setCursor(QCursor(Qt.PointingHandCursor))

    def set_anim_state(self, state):
        """设置动画状态: idle, listening, wake_detected, command_listening, processing, speaking, paused"""
        self._anim_state = state
        self._anim_phase = 0
        if state == "idle":
            self._anim_timer.stop()
        elif state == "listening":
            self._anim_timer.start(500)
        elif state == "wake_detected":
            self._anim_timer.start(150)
        elif state == "command_listening":
            self._anim_timer.start(300)
        elif state == "processing":
            self._anim_timer.start(100)
        elif state == "speaking":
            self._anim_timer.start(400)
        elif state == "paused":
            self._anim_timer.stop()
        self.update()

    def _tick_anim(self):
        self._anim_phase += 1
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setPen(Qt.NoPen)
        s = self.width()

        state = self._anim_state
        phase = self._anim_phase

        # 背景色
        if state == "listening":
            # 绿色呼吸脉冲
            alpha = 180 + int(75 * abs((phase % 4) - 2) / 2)
            bg = QColor(34, 197, 94, alpha)
        elif state == "wake_detected":
            # 白色闪烁
            bg = QColor(255, 255, 255, 200) if phase % 2 == 0 else QColor(34, 197, 94, 200)
        elif state == "command_listening":
            # 蓝色脉冲
            alpha = 180 + int(75 * abs((phase % 4) - 2) / 2)
            bg = QColor(59, 130, 246, alpha)
        elif state == "processing":
            # 蓝灰色
            bg = QColor(100, 116, 139, 200)
        elif state == "speaking":
            # 蓝色发光
            bg = QColor(59, 130, 246, 200).lighter(115) if phase % 2 == 0 else QColor(59, 130, 246, 200)
        elif state == "paused":
            # 灰色（禁用状态）
            bg = QColor(120, 120, 120, 180)
        elif self._pressed:
            bg = QColor("#92400E")
        elif self._hovered:
            bg = QColor("#B85C00")
        else:
            bg = QColor("#D97706")

        p.setBrush(QBrush(bg))
        p.drawEllipse(0, 0, s, s)

        # processing: 旋转弧
        if state == "processing":
            p.setPen(QPen(Qt.white, 2.5))
            p.setBrush(Qt.NoBrush)
            span = 90 * 16
            start = (phase * 30) % 360
            p.drawArc(4, 4, s - 8, s - 8, start * 16, span)
        elif state == "idle":
            # 矢量绘制 "C" 字母
            p.setPen(QPen(Qt.white, max(2, s // 10)))
            p.setBrush(Qt.NoBrush)
            p.setFont(QFont("Arial", max(10, int(s * 0.48)), QFont.Bold))
            p.drawText(0, 0, s, s, Qt.AlignCenter, "C")
        elif state == "paused":
            # 禁用麦克风图标：麦克风 + 斜杠
            p.setPen(QPen(QColor(200, 200, 200), 2))
            cx, cy = s / 2, s / 2
            # 麦克风图标
            mic_w, mic_h = s * 0.16, s * 0.28
            p.setBrush(QBrush(QColor(200, 200, 200)))
            p.drawRoundedRect(int(cx - mic_w), int(cy - mic_h), int(mic_w * 2), int(mic_h * 2), 3, 3)
            # 底部弧线
            p.setBrush(Qt.NoBrush)
            arc_r = s * 0.22
            p.drawArc(int(cx - arc_r), int(cy - mic_h * 0.3), int(arc_r * 2), int(arc_r * 2), 0, 180 * 16)
            # 底部竖线
            p.drawLine(int(cx), int(cy + arc_r * 0.7), int(cx), int(cy + arc_r * 1.1))
            # 斜杠（禁用标志）
            p.setPen(QPen(QColor(255, 80, 80), 2.5))
            slash_len = s * 0.35
            p.drawLine(int(cx - slash_len), int(cy + slash_len), int(cx + slash_len), int(cy - slash_len))
        else:
            # listening / wake_detected / command_listening / speaking: 麦克风图标
            p.setPen(QPen(Qt.white, 2))
            cx, cy = s / 2, s / 2
            # 简化的麦克风图标
            mic_w, mic_h = s * 0.16, s * 0.28
            p.setBrush(QBrush(Qt.white))
            p.drawRoundedRect(int(cx - mic_w), int(cy - mic_h), int(mic_w * 2), int(mic_h * 2), 3, 3)
            # 底部弧线
            p.setBrush(Qt.NoBrush)
            arc_r = s * 0.22
            p.drawArc(int(cx - arc_r), int(cy - mic_h * 0.3), int(arc_r * 2), int(arc_r * 2), 0, 180 * 16)
            # 底部竖线
            p.drawLine(int(cx), int(cy + arc_r * 0.7), int(cx), int(cy + arc_r * 1.1))

        p.end()

    def enterEvent(self, event):
        self._hovered = True; self.update()

    def leaveEvent(self, event):
        self._hovered = False; self.update()

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._pressed = True
            self._drag_start = event.globalPosition().toPoint()
            w = self.window()
            self._drag_win_origin = w.pos()
            self.update()
            event.accept()
        elif event.button() == Qt.RightButton:
            self.right_clicked.emit()
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
                border-radius: 10px;
            }
            QScrollArea { background:transparent; border:none; }
            QPushButton {
                background:#4ECDC4; color:white; border:none; border-radius:6px;
                padding:6px 12px; font-family:"Microsoft YaHei UI";
            }
            QPushButton:hover { background:#5fd9d2; }
            QPushButton:pressed { background:#3dbdb5; }
            QLineEdit {
                background:#1a2029; color:white; border:1px solid #3a4555;
                border-radius:6px; padding:6px 10px; font-family:"Microsoft YaHei UI";
            }
            QLineEdit:focus { border:1px solid #4ECDC4; }
        """)
        self.setAttribute(Qt.WA_StyledBackground)
        self._corner_radius = 10
        self._dragging = False
        self._drag_start = QPoint()
        self._drag_win_origin = QPoint()

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
        header.setStyleSheet("background:#1a2029; border:none; border-top-left-radius:10px; border-top-right-radius:10px;")
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
        iw.setStyleSheet("background:#1a2029; border:none; border-bottom-left-radius:10px; border-bottom-right-radius:10px;")
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
        self.tts_btn = QPushButton("🔊 朗读")
        self.tts_btn.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Preferred)
        self.tts_btn.clicked.connect(self._on_tts_btn_click)
        row2.addWidget(self.tts_btn, 1)

        il.addLayout(row1)
        il.addLayout(row2)
        ml.addWidget(iw)

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setBrush(QColor("#2b3441"))
        p.setPen(QPen(QColor("#3a4555"), 1))
        p.drawRoundedRect(self.rect().adjusted(1, 1, -1, -1),
                          self._corner_radius, self._corner_radius)
        p.end()

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton and event.position().y() < 44:
            self._dragging = True
            self._drag_start = event.globalPosition().toPoint()
            self._drag_win_origin = self.window().pos()
            event.accept()
        else:
            super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._dragging:
            delta = event.globalPosition().toPoint() - self._drag_start
            self.window().move(self._drag_win_origin + delta)
            event.accept()
        else:
            super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton and self._dragging:
            self._dragging = False
            event.accept()
        else:
            super().mouseReleaseEvent(event)

    def _on_send(self):
        text = self.input_box.text().strip()
        _log(f"[SEND] text='{text}'")
        if not text:
            return
        self.input_box.clear()
        self._main._on_user_message(text)

    def _on_tts_btn_click(self):
        if self._main._tts_playing:
            # 立即更新按钮状态
            self._main._tts_playing = False
            self._main._set_tts_btn_playing(False)
            self._main._stop_tts()
        else:
            self._main._speak_last()

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
#  Pill Menu (右键药丸菜单)
# ═══════════════════════════════════════════════════════════════════
class PillMenu(QWidget):
    PILL_MENU_W = 210
    PILL_MENU_H = 56

    def __init__(self, main_widget, parent=None):
        super().__init__(parent)
        self._main = main_widget
        self._mic_active = True  # 默认麦克风开启
        self.setFixedSize(self.PILL_MENU_W, self.PILL_MENU_H)
        self.setAttribute(Qt.WA_TranslucentBackground, False)
        self.setAutoFillBackground(False)

        btn_style = """
            QPushButton {
                background: transparent;
                color: #ffffff;
                border: none;
                border-radius: 20px;
                padding: 8px 12px;
                font-family: "Microsoft YaHei UI";
                font-size: 13pt;
            }
            QPushButton:hover { background: rgba(255,255,255,0.2); }
            QPushButton:pressed { background: rgba(255,255,255,0.3); }
        """

        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 4, 10, 4)
        layout.setSpacing(2)

        self.mic_btn = QPushButton("🎤")
        self.mic_btn.setFixedSize(48, 40)
        self.mic_btn.setToolTip("禁用麦克风")  # 默认开启，所以显示禁用
        self.mic_btn.setStyleSheet(btn_style)
        self.mic_btn.clicked.connect(self._toggle_mic)

        self.settings_btn = QPushButton("⚙")
        self.settings_btn.setFixedSize(48, 40)
        self.settings_btn.setToolTip("设置")
        self.settings_btn.setStyleSheet(btn_style)
        self.settings_btn.clicked.connect(self._open_settings)

        close_btn = QPushButton("✕")
        close_btn.setFixedSize(48, 40)
        close_btn.setToolTip("退出程序")
        close_btn.setStyleSheet("""
            QPushButton {
                background: transparent;
                color: #ffffff;
                border: none;
                border-radius: 20px;
                font-size: 14pt;
                font-weight: bold;
            }
            QPushButton:hover { background: rgba(255,255,255,0.2); }
            QPushButton:pressed { background: rgba(255,255,255,0.3); }
        """)
        close_btn.clicked.connect(self._quit_app)

        layout.addWidget(self.mic_btn)
        layout.addWidget(self.settings_btn)
        layout.addWidget(close_btn)

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        color = QColor("#D97706")
        r = self.rect()
        # 用带同色边框的画笔消除抗锯齿白边
        pen = QPen(color, 2)
        pen.setJoinStyle(Qt.RoundJoin)
        p.setPen(pen)
        p.setBrush(color)
        p.drawRoundedRect(r.adjusted(1, 1, -1, -1), 28, 28)
        p.end()

    def _toggle_mic(self):
        pipeline = getattr(self._main, '_pipeline', None)
        if not pipeline:
            return
        if self._mic_active:
            # 禁用麦克风
            self._mic_active = False
            self.mic_btn.setText("🔇")
            self.mic_btn.setToolTip("启用麦克风")
            pipeline.stop()
            self._main._circle.set_anim_state("paused")
        else:
            # 启用麦克风
            self._mic_active = True
            self.mic_btn.setText("🎤")
            self.mic_btn.setToolTip("禁用麦克风")
            pipeline.start()
            self._main._circle.set_anim_state("idle")
        self.update()

    def _open_settings(self):
        self._main._hide_pill_menu()
        self._main._show_settings()

    def _quit_app(self):
        # 停止管线（会终止 TTS 和 ffplay 进程）
        if self._main._pipeline:
            self._main._pipeline.stop()
        # 杀掉所有残留的 ffplay 进程
        try:
            subprocess.run(["taskkill", "/F", "/IM", "ffplay.exe"],
                           capture_output=True, timeout=3,
                           creationflags=subprocess.CREATE_NO_WINDOW)
        except Exception:
            pass
        QApplication.quit()


# ═══════════════════════════════════════════════════════════════════
#  Settings Dialog
# ═══════════════════════════════════════════════════════════════════
class SettingsDialog(QWidget):
    def __init__(self, main_widget, parent=None):
        super().__init__(parent)
        self._main = main_widget
        self.setWindowTitle("设置")
        self.setFixedSize(360, 385)
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground)

        # 配置文件路径
        self._config_file = os.path.join(os.path.dirname(__file__), "settings.json")
        self._config = self._load_config()

        self._init_ui()
        self._apply_config()

    def _load_config(self):
        default = {
            "mic_device": "",
            "mute_tts": False,
            "wake_word": "小助手",
            "audio_url": "http://192.168.1.32:9997",
            "ollama_url": "http://192.168.1.32:11434",
            "ollama_model": "qwen3-vl:4b",
        }
        try:
            if os.path.exists(self._config_file):
                with open(self._config_file, "r", encoding="utf-8") as f:
                    cfg = json.load(f)
                for k, v in default.items():
                    if k not in cfg:
                        cfg[k] = v
                return cfg
        except Exception:
            pass
        return default

    def _save_config(self):
        try:
            with open(self._config_file, "w", encoding="utf-8") as f:
                json.dump(self._config, f, ensure_ascii=False, indent=2)
        except Exception as e:
            _log(f"[设置] 保存失败: {e}")

    def _init_ui(self):
        # 外层容器（带圆角背景）
        container = QWidget(self)
        container.setGeometry(0, 0, self.width(), self.height())
        container.setStyleSheet("""
            QWidget {
                background: #2b3441;
                border: 1px solid #3a4555;
                border-radius: 10px;
            }
            QLabel { color: #e0e0e0; background: transparent; border: none; font-family: "Microsoft YaHei UI"; }
            QComboBox {
                background: #1a2029; color: white; border: 1px solid #3a4555;
                border-radius: 6px; padding: 5px 8px; font-family: "Microsoft YaHei UI";
            }
            QComboBox:focus { border: 1px solid #4ECDC4; }
            QComboBox QAbstractItemView { background: #1a2029; color: white; selection-background-color: #4ECDC4; }
            QLineEdit {
                background: #1a2029; color: white; border: 1px solid #3a4555;
                border-radius: 6px; padding: 5px 8px; font-family: "Microsoft YaHei UI";
            }
            QLineEdit:focus { border: 1px solid #4ECDC4; }
            QCheckBox { color: #e0e0e0; background: transparent; border: none; font-family: "Microsoft YaHei UI"; }
            QCheckBox::indicator { width: 16px; height: 16px; }
            QPushButton {
                background: #4ECDC4; color: white; border: none;
                border-radius: 6px; padding: 6px 16px; font-family: "Microsoft YaHei UI";
            }
            QPushButton:hover { background: #5fd9d2; }
            QPushButton:pressed { background: #3dbdb5; }
        """)

        ml = QVBoxLayout(container)
        ml.setContentsMargins(16, 16, 16, 16)
        ml.setSpacing(10)

        # 标题栏
        header = QHBoxLayout()
        title = QLabel("设置")
        title.setFont(QFont("Microsoft YaHei UI", 11, QFont.Bold))
        spacer = QWidget()
        spacer.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        spacer.setAttribute(Qt.WA_TranslucentBackground)
        close_btn = QPushButton()
        close_btn.setFixedSize(22, 22)
        # 绘制白色 X 图标
        x_icon = QPixmap(12, 12)
        x_icon.fill(Qt.transparent)
        _p = QPainter(x_icon)
        _p.setRenderHint(QPainter.Antialiasing)
        _p.setPen(QPen(QColor("white"), 2))
        _p.drawLine(2, 2, 10, 10)
        _p.drawLine(10, 2, 2, 10)
        _p.end()
        close_btn.setIcon(QIcon(x_icon))
        close_btn.setIconSize(QSize(12, 12))
        close_btn.setStyleSheet("""
            QPushButton {
                background: #D97706; border: none;
                border-radius: 11px;
            }
            QPushButton:hover { background: #e88a1a; }
            QPushButton:pressed { background: #c06a06; }
        """)
        close_btn.clicked.connect(self.hide)
        header.addWidget(title)
        header.addWidget(spacer)
        header.addWidget(close_btn)
        ml.addLayout(header)

        # 1. 麦克风选择
        ml.addWidget(QLabel("麦克风设备"))
        self._mic_combo = QComboBox()
        self._mic_combo.setMinimumWidth(280)
        self._mic_combo.setFixedHeight(26)
        self._refresh_mic_list()
        ml.addWidget(self._mic_combo)

        # 2. 禁止自动朗读
        self._mute_cb = QCheckBox("禁止自动朗读（TTS）")
        ml.addWidget(self._mute_cb)

        # 3. 唤醒词
        ml.addWidget(QLabel("唤醒词"))
        self._wake_word_edit = QLineEdit()
        self._wake_word_edit.setFixedHeight(26)
        self._wake_word_edit.setPlaceholderText("小助手")
        ml.addWidget(self._wake_word_edit)

        # 4. Audio 服务 URL
        ml.addWidget(QLabel("Audio 服务 URL"))
        self._audio_url_edit = QLineEdit()
        self._audio_url_edit.setFixedHeight(26)
        ml.addWidget(self._audio_url_edit)

        # 4. Ollama URL + 模型下拉
        ml.addWidget(QLabel("Ollama 服务 URL"))
        self._ollama_url_edit = QLineEdit()
        self._ollama_url_edit.setFixedHeight(26)
        self._ollama_url_edit.editingFinished.connect(self._refresh_model_list)
        ml.addWidget(self._ollama_url_edit)

        ml.addWidget(QLabel("模型名称"))
        self._ollama_model_combo = QComboBox()
        self._ollama_model_combo.setMinimumWidth(280)
        self._ollama_model_combo.setFixedHeight(26)
        ml.addWidget(self._ollama_model_combo)

        # 保存按钮
        btn_row = QHBoxLayout()
        btn_row.addStretch()
        save_btn = QPushButton("保存")
        save_btn.setFixedHeight(25)
        save_btn.setStyleSheet("""
            QPushButton {
                background: #D97706; color: white; border: none;
                border-radius: 6px; padding: 6px 16px;
            }
            QPushButton:hover { background: #e88a1a; }
            QPushButton:pressed { background: #c06a06; }
        """)
        save_btn.clicked.connect(self._on_save)
        btn_row.addWidget(save_btn)
        ml.addLayout(btn_row)

    def _refresh_mic_list(self):
        self._mic_combo.clear()
        self._mic_combo.addItem("默认麦克风", "")
        try:
            devices = sd.query_devices()
            for i, d in enumerate(devices):
                if d["max_input_channels"] > 0:
                    name = d["name"]
                    self._mic_combo.addItem(f"{name}", str(i))
        except Exception as e:
            _log(f"[设置] 枚举麦克风失败: {e}")

    def _refresh_model_list(self):
        """从 Ollama 服务器获取可用模型列表"""
        self._ollama_model_combo.clear()
        url = self._ollama_url_edit.text().strip() or "http://192.168.1.32:11434"
        try:
            resp = urlopen(f"{url}/api/tags", timeout=3)
            data = json.loads(resp.read().decode("utf-8"))
            models = data.get("models", [])
            for m in models:
                name = m.get("name", "")
                if name:
                    self._ollama_model_combo.addItem(name)
        except Exception as e:
            _log(f"[设置] 获取模型列表失败: {e}")
            # 回退：至少显示配置中的模型
            saved = self._config.get("ollama_model", "qwen3-vl:4b")
            self._ollama_model_combo.addItem(saved)

    def _apply_config(self):
        # 麦克风
        mic = self._config.get("mic_device", "")
        idx = self._mic_combo.findData(mic)
        if idx >= 0:
            self._mic_combo.setCurrentIndex(idx)
        # 静音
        self._mute_cb.setChecked(self._config.get("mute_tts", False))
        # 唤醒词
        self._wake_word_edit.setText(self._config.get("wake_word", "小助手"))
        # URL
        self._audio_url_edit.setText(self._config.get("audio_url", SERVER_URL))
        self._ollama_url_edit.setText(self._config.get("ollama_url", SERVER_URL))
        # 模型列表
        self._refresh_model_list()
        saved_model = self._config.get("ollama_model", "qwen3-vl:4b")
        idx = self._ollama_model_combo.findText(saved_model)
        if idx >= 0:
            self._ollama_model_combo.setCurrentIndex(idx)

    def _on_save(self):
        self._config["mic_device"] = self._mic_combo.currentData() or ""
        self._config["mute_tts"] = self._mute_cb.isChecked()
        self._config["wake_word"] = self._wake_word_edit.text().strip() or "小助手"
        self._config["audio_url"] = self._audio_url_edit.text().strip() or SERVER_URL
        self._config["ollama_url"] = self._ollama_url_edit.text().strip() or SERVER_URL
        self._config["ollama_model"] = self._ollama_model_combo.currentText() or "qwen3-vl:4b"
        self._save_config()
        self._apply_to_main()
        self.hide()

    def _apply_to_main(self):
        """将配置应用到 MainWidget 和 Pipeline"""
        # TTS 静音
        mute = self._config.get("mute_tts", False)
        self._main._tts_muted = mute
        # Pipeline 麦克风设备 + 模型 + 静音 + 唤醒词
        if self._main._pipeline:
            self._main._pipeline._mic_device = self._config.get("mic_device", None)
            self._main._pipeline._model = self._config.get("ollama_model", "qwen3-vl:4b")
            self._main._pipeline._tts_muted = mute
            self._main._pipeline._wake_word = self._config.get("wake_word", "小助手")

    def showEvent(self, event):
        """每次显示时重新加载配置，丢弃未保存的修改"""
        self._config = self._load_config()
        self._apply_config()
        super().showEvent(event)

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setBrush(QColor("#2b3441"))
        p.setPen(QPen(QColor("#3a4555"), 1))
        p.drawRoundedRect(self.rect().adjusted(1, 1, -1, -1), 10, 10)
        p.end()

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._dragging = True
            self._drag_start = event.globalPosition().toPoint()
            self._drag_win_origin = self.pos()

    def mouseMoveEvent(self, event):
        if hasattr(self, '_dragging') and self._dragging:
            delta = event.globalPosition().toPoint() - self._drag_start
            self.move(self._drag_win_origin + delta)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._dragging = False


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
    sig_chat = Signal(str)        # 跨线程触发对话

    def __init__(self, pipeline=None):
        super().__init__()
        self._expanded = False
        self._pill_shown = False
        self._chat_cancelled = False
        self._ai_bubble = None
        self._stream_buf = ""
        self._stream_dirty = False
        self._greeting_shown = False
        self._last_ai_text = ""
        self._tts_muted = False
        self._tts_playing = False   # TTS 是否正在播放
        self._pipeline = pipeline

        # 设置对话框（加载已保存的配置并应用）
        self._settings_dialog = SettingsDialog(self)
        self._settings_dialog._apply_to_main()

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
        self._circle.right_clicked.connect(self._show_pill_menu)
        self._stack.addWidget(self._circle)

        # 页面 1：聊天面板
        self._panel = ChatPanel(self)
        self._panel.hide()
        self._stack.addWidget(self._panel)

        # 页面 2：药丸菜单（右键弹出）
        self._pill_menu = PillMenu(self)
        self._pill_menu.hide()
        self._stack.addWidget(self._pill_menu)

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
        self.sig_chat.connect(self._chat_with_ai)

        # 连接管线信号
        if self._pipeline:
            self._pipeline.state_changed.connect(self._on_pipeline_state)
            self._pipeline.wake_word_detected.connect(self._on_wake_word)
            self._pipeline.command_captured.connect(self._on_pipeline_command)
            self._pipeline.ai_response_stream.connect(self._on_stream_token)
            self._pipeline.ai_response_done.connect(self._on_ai_done)
            self._pipeline.tts_start.connect(self._on_tts_start)
            self._pipeline.tts_done.connect(self._on_tts_done)
            self._pipeline.error_occurred.connect(self._on_pipeline_error)

        # 初始：只显示圆形
        self.setFixedSize(self.BUBBLE_DIA, self.BUBBLE_DIA)
        self._move_to_corner()
        self.show()

    def _move_to_corner(self):
        screen = QApplication.primaryScreen()
        if screen:
            geo = screen.availableGeometry()  # 排除任务栏区域
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

        # 暂停绘制，窗口保持原位
        self.setUpdatesEnabled(False)

        # 窗口扩到最终大小（但不移动位置，避免闪到新位置）
        self.setMinimumSize(self.PILL_W, self.PILL_H)
        self.setMaximumSize(self.PILL_W, self.PILL_H)
        self._panel.show()
        self._stack.setCurrentIndex(1)
        QApplication.processEvents()

        pixmap = self._grab_panel()

        self._panel.hide()
        self._anim_label.setPixmap(pixmap)
        self._anim_label.setGeometry(
            self.PILL_W - self.BUBBLE_DIA,
            self.PILL_H - self.BUBBLE_DIA,
            self.BUBBLE_DIA, self.BUBBLE_DIA
        )
        self._anim_label.show()

        self.setUpdatesEnabled(True)

        # 同时做：窗口位置动画 + 截图缩放动画
        win_anim = QPropertyAnimation(self, b"pos")
        win_anim.setDuration(self.ANIM_MS)
        win_anim.setStartValue(start_pos)
        win_anim.setEndValue(QPoint(target_x, target_y))
        win_anim.setEasingCurve(QEasingCurve.OutCubic)

        label_anim = QPropertyAnimation(self._anim_label, b"geometry")
        label_anim.setDuration(self.ANIM_MS)
        label_anim.setEndValue(QRect(0, 0, self.PILL_W, self.PILL_H))
        label_anim.setEasingCurve(QEasingCurve.OutCubic)

        self._expand_group = QParallelAnimationGroup()
        self._expand_group.addAnimation(win_anim)
        self._expand_group.addAnimation(label_anim)
        self._expand_group.finished.connect(self._on_expand_done)
        self._expand_group.start()

    def _on_expand_done(self):
        self._anim_label.hide()
        self._anim_label.clear()
        self._panel._opacity_effect.setOpacity(1.0)
        self._panel.show()
        self._circle.hide()
        self._panel.input_box.setFocus()
        if not self._greeting_shown:
            self._greeting_shown = True
            self._panel.add_bubble("您好，我是您的AI助手，我能帮您调节亮度、对比度、音量等，您可以跟我说“小助手，帮我把亮度调高一些”。", False)

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
        self._circle.show()
        # 根据面板当前位置计算悬浮球位置（右下角）
        panel_pos = self.pos()
        ball_pos = QPoint(
            panel_pos.x() + self.PILL_W - self.BUBBLE_DIA,
            panel_pos.y() + self.PILL_H - self.BUBBLE_DIA,
        )
        self._ball_pos = ball_pos
        self.setFixedSize(self.BUBBLE_DIA, self.BUBBLE_DIA)
        self.setMinimumSize(0, 0)
        self.setMaximumSize(16777215, 16777215)
        self.move(ball_pos)

    # ── 药丸菜单 ────────────────────────────────────────────
    def _show_pill_menu(self):
        if self._pill_shown:
            self._hide_pill_menu()
            return
        if self._expanded:
            return
        self._pill_shown = True

        start_pos = self.pos()
        self._ball_pos = start_pos
        pw = PillMenu.PILL_MENU_W
        ph = PillMenu.PILL_MENU_H
        target_x = max(0, start_pos.x() + self.BUBBLE_DIA - pw)
        target_y = start_pos.y()

        # 直接调整窗口大小并显示药丸，无需截图动画
        self.setFixedSize(pw, ph)
        self._stack.setCurrentIndex(2)
        self._pill_menu.show()

        # 位置滑入动画
        anim = QPropertyAnimation(self, b"pos")
        anim.setDuration(self.ANIM_MS)
        anim.setStartValue(start_pos)
        anim.setEndValue(QPoint(target_x, target_y))
        anim.setEasingCurve(QEasingCurve.OutCubic)
        self._pill_anim = anim
        anim.start()

    def _show_settings(self):
        """显示设置对话框"""
        dlg = self._settings_dialog
        # 获取悬浮球位置和尺寸
        ball_pos = self._circle.mapToGlobal(QPoint(0, 0))
        ball_rect = self._circle.geometry()
        ball_cx = ball_pos.x() + ball_rect.width() // 2
        ball_top = ball_pos.y()
        ball_bottom = ball_pos.y() + ball_rect.height()

        # 屏幕几何信息
        screen = QApplication.primaryScreen().availableGeometry()

        # 设置对话框位置：优先显示在悬浮球上方
        dlg_w = dlg.width()
        dlg_h = dlg.height()
        x = ball_cx - dlg_w // 2

        # 检查上方空间是否足够
        space_above = ball_top - screen.top()
        if space_above >= dlg_h + 10:
            y = ball_top - dlg_h - 10
        else:
            # 上方不够，显示在下方
            y = ball_bottom + 10

        # 确保不超出屏幕边界
        x = max(screen.left(), min(x, screen.right() - dlg_w))
        y = max(screen.top(), min(y, screen.bottom() - dlg_h))

        dlg.move(x, y)
        dlg.show()
        dlg.raise_()
        dlg.activateWindow()

    def _hide_pill_menu(self):
        if not self._pill_shown:
            return
        self._pill_shown = False

        target_pos = getattr(self, '_ball_pos', self.pos())

        # 位置滑出动画
        anim = QPropertyAnimation(self, b"pos")
        anim.setDuration(self.ANIM_MS)
        anim.setEndValue(target_pos)
        anim.setEasingCurve(QEasingCurve.InCubic)
        self._pill_hide_anim = anim
        anim.finished.connect(self._on_pill_hide_done)
        anim.start()

    def _on_pill_hide_done(self):
        self._pill_menu.hide()
        self._stack.setCurrentIndex(0)
        self.setFixedSize(self.BUBBLE_DIA, self.BUBBLE_DIA)
        self.setMinimumSize(0, 0)
        self.setMaximumSize(16777215, 16777215)
        if hasattr(self, '_ball_pos'):
            self.move(self._ball_pos)

    def mousePressEvent(self, event):
        if self._pill_shown and event.button() == Qt.LeftButton:
            pos_in_menu = self._pill_menu.mapFromGlobal(event.globalPosition().toPoint())
            if not self._pill_menu.rect().contains(pos_in_menu):
                self._hide_pill_menu()
                event.accept()
                return
        super().mousePressEvent(event)

    def changeEvent(self, event):
        if self._pill_shown and event.type() == event.Type.ActivationChange:
            if not self.isActiveWindow():
                self._hide_pill_menu()
        super().changeEvent(event)

    # ── 聊天 ──────────────────────────────────────────────────
    def _on_user_message(self, text):
        self._panel.add_bubble(text, True)
        # 意图识别：正则快速匹配
        intent = parse_voice_command(text)
        if intent:
            self._exec_display_control(intent)
            return
        # 正则未命中，用 LLM 纠错兜底（在后台线程执行，不阻塞 UI）
        if self._pipeline:
            self._panel.status_lbl.setText("正在识别意图...")
            threading.Thread(target=self._intent_detect_and_dispatch,
                             args=(text,), daemon=True).start()
        else:
            self._chat_with_ai(text)

    def _intent_detect_and_dispatch(self, text):
        """后台线程：LLM 意图识别 → 执行或走对话"""
        try:
            # Regex 已在 _on_user_message 中尝试过，这里用 LLM 兜底
            intents = self._pipeline._llm_intent_detect(text)
            if intents:
                self._exec_display_control_sync(intents)
            else:
                self.sig_chat.emit(text)
        except Exception as e:
            _log(f"[意图] LLM 识别异常: {e}")
            self.sig_chat.emit(text)

    def _exec_display_control(self, intent):
        """执行显示器控制命令（文字输入触发）"""
        def _do():
            try:
                if self._pipeline:
                    reply = self._pipeline._execute_display_control(intent)
                else:
                    reply = "管线未启动"
                self.sig_stream.emit(reply)
                self.sig_done.emit(reply)
                # TTS 播放回复
                if self._pipeline and not self._tts_muted:
                    self._pipeline.speak_text(reply)
            except Exception as e:
                self.sig_error.emit(str(e))
        threading.Thread(target=_do, daemon=True).start()

    def _exec_display_control_sync(self, intents):
        """执行显示器控制命令（已在后台线程中，直接执行）"""
        try:
            replies = []
            for intent in intents:
                if self._pipeline:
                    reply = self._pipeline._execute_display_control(intent)
                else:
                    reply = "管线未启动"
                replies.append(reply)
            full_reply = "，".join(replies)
            self.sig_stream.emit(full_reply)
            self.sig_done.emit(full_reply)
            # TTS 播放回复
            if self._pipeline and not self._tts_muted:
                self._pipeline.speak_text(full_reply)
        except Exception as e:
            self.sig_error.emit(str(e))

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
        tts_started = False
        sentence_buffer = ""
        sentence_end_chars = set("。！？；\n.!?;")
        try:
            # 1. 预检：快速检测 ollama 是否可达（3 秒超时，快速失败）
            try:
                pre = Request("http://127.0.0.1:18766/ollama/api/tags",
                              headers={"Content-Type": "application/json"})
                urlopen(pre, timeout=3).close()
            except Exception as e:
                _log(f"[CHAT] 预检失败: {e}")
                self.sig_error.emit(f"AI 服务不可达: {e}")
                return

            self.sig_status.emit("模型加载中...")

            # 2. 正式请求：使用 urllib（比 http.client 对 GIL 更友好）
            model = self._pipeline._model if self._pipeline else "qwen3-vl:4b"
            payload = json.dumps({
                "model": model,
                "messages": [{"role": "user", "content": text}],
                "stream": True
            }).encode()

            req = Request("http://127.0.0.1:18766/ollama/api/chat",
                          data=payload,
                          headers={"Content-Type": "application/json"},
                          method="POST")
            resp = urlopen(req, timeout=90)

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
                            sentence_buffer += token
                            token_count += 1
                            # 每 5 个 token emit 一次，减少主线程信号队列压力
                            if token_count % 5 == 0 or token_count == 1:
                                self.sig_stream.emit(full)

                            # 流式 TTS：首 token 启动 TTS，句子完成时送入队列
                            if not self._tts_muted and self._pipeline:
                                if not tts_started:
                                    tts_started = True
                                    self._pipeline._interrupted = False
                                    self._pipeline.notify_tts_start()
                                    self._pipeline._start_tts_workers()
                                # 检查句子是否完成
                                if token and token[-1] in sentence_end_chars:
                                    sentence = sentence_buffer.strip()
                                    if sentence:
                                        clean = _strip_md(sentence)
                                        if clean:
                                            self._pipeline._sentence_queue.append(clean)
                                        sentence_buffer = ""
                    except json.JSONDecodeError:
                        continue

            resp.close()

            # 处理剩余的句子缓冲
            if sentence_buffer.strip() and not self._chat_cancelled and tts_started:
                clean = _strip_md(sentence_buffer.strip())
                if clean:
                    self._pipeline._sentence_queue.append(clean)

            # 发送结束信号到 TTS
            if tts_started and self._pipeline:
                self._pipeline._sentence_queue.append(None)

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
        self._wait_timer.stop()
        self._flush_timer.stop()
        # 强制用最终文本更新气泡（忽略 dirty 标记）
        if self._ai_bubble and full:
            self._ai_bubble.setText(full)
            self._panel._scroll_to_bottom()
        self._panel.status_lbl.setText("")
        self._ai_bubble = None
        if full:
            self._last_ai_text = full

    def _on_ai_error(self, err):
        self._wait_timer.stop()
        self._flush_timer.stop()
        self._panel.status_lbl.setText("")
        self._panel.add_bubble(f"[错误] {err}", False)

    def _speak_last(self):
        """重新朗读上次的AI回复（通过管线）"""
        if not self._last_ai_text:
            self._panel.status_lbl.setText("没有可朗读的内容")
            return
        if self._pipeline:
            clean = _strip_md(self._last_ai_text)
            if not clean:
                self._panel.status_lbl.setText("没有可朗读的内容")
                return
            self._pipeline.speak_text(clean)

    def _stop_tts(self):
        """停止当前 TTS 播放"""
        if self._pipeline:
            self._pipeline._interrupt()
            self._pipeline._set_state("idle")

    # ── 管线状态处理 ──────────────────────────────────────────
    def _on_pipeline_state(self, state):
        """管线状态变化，更新 UI"""
        self._circle.set_anim_state(state)
        state_text = {
            "idle": "",
            "listening": "正在聆听...",
            "wake_detected": "唤醒词检测到!",
            "command_listening": "正在听取指令...",
            "processing": "思考中...",
            "speaking": "",
            "paused": "已暂停",
        }
        self._panel.status_lbl.setText(state_text.get(state, ""))
        # TTS 播放期间不更新按钮状态（由 _tts_playing 控制）
        if not self._tts_playing:
            self._set_tts_btn_playing(state == "speaking")

    def _on_wake_word(self, word):
        """唤醒词检测到，自动展开面板"""
        _flog(f"[唤醒] 检测到: {word}")
        if not self._expanded:
            self._expand()

    def _on_pipeline_command(self, text):
        """管线识别到指令，只显示气泡（不触发 LLM，管线内部已处理）"""
        self._panel.add_bubble(text, True)

    def _on_pipeline_error(self, err):
        """管线错误"""
        _flog(f"[管线] 错误: {err}")
        self._panel.status_lbl.setText(f"错误: {err[:50]}")

    def _on_tts_start(self):
        """TTS 开始播放"""
        self._tts_playing = True
        self._set_tts_btn_playing(True)

    def _on_tts_done(self):
        """TTS 播放完成"""
        self._tts_playing = False
        self._set_tts_btn_playing(False)

    def _set_tts_btn_playing(self, playing):
        if playing:
            self._panel.tts_btn.setText("⏹ 停止朗读")
            self._panel.tts_btn.setStyleSheet(
                "background:#ef4444; color:white; border:none; border-radius:6px;"
                "padding:6px 12px; font-family:\"Microsoft YaHei UI\";"
            )
        else:
            self._panel.tts_btn.setText("🔊 朗读")
            self._panel.tts_btn.setStyleSheet("")


# ═══════════════════════════════════════════════════════════════════
#  Main
# ═══════════════════════════════════════════════════════════════════
def run_server():
    import server
    server.main()


def main():
    # 无控制台模式：将 stderr 重定向到日志文件
    if sys.stderr is None or not hasattr(sys.stderr, 'fileno') or sys.stderr.fileno() < 0:
        sys.stderr = open(_log_path, "a", encoding="utf-8")

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

    # 创建语音管线
    from voice_pipeline import VoicePipeline
    pipeline = VoicePipeline(wake_word="小助手", server_url=SERVER_URL)

    w = MainWidget(pipeline=pipeline)

    # 启动管线
    pipeline.start()

    def _cleanup():
        pipeline.stop()
        try:
            subprocess.run(["taskkill", "/F", "/IM", "ffplay.exe"],
                           capture_output=True, timeout=3,
                           creationflags=subprocess.CREATE_NO_WINDOW)
        except Exception:
            pass

    app.aboutToQuit.connect(_cleanup)
    app.aboutToQuit.connect(w.close)
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
