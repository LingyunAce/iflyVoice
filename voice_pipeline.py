#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
常开麦克风语音管线：VAD → 唤醒词检测 → 语音识别 → LLM → TTS（实时流式）
"""
import sys, os, json, time, threading, tempfile, uuid, subprocess, http.client, collections, re
import numpy as np
import sounddevice as sd

from urllib.request import urlopen, Request
from urllib.error import HTTPError
from PySide6.QtCore import QObject, Signal

# ── 日志 ─────────────────────────────────────────────────────────
def _log(msg):
    print(f"[Pipeline] {msg}", file=sys.stderr, flush=True)

_log_path = os.path.join(os.path.dirname(__file__), "widget.log")
_log_file = open(_log_path, "a", encoding="utf-8")

def _flog(msg):
    ts = time.strftime("%H:%M:%S")
    ms = int(time.time() * 1000) % 1000
    line = f"{ts}.{ms:03d} {msg}"
    _log_file.write(line + "\n")
    _log_file.flush()
    print(f"[Pipeline] {line}", file=sys.stderr, flush=True)


# ── 文本清理 ─────────────────────────────────────────────────────
def _strip_md(text):
    """去掉 markdown 格式符号，保留纯文本内容供 TTS 朗读"""
    if not text:
        return text
    s = text
    # 代码块 ```...``` → 去掉
    s = re.sub(r'```[\s\S]*?```', '', s)
    # 行内代码 `...` → 保留内容
    s = re.sub(r'`([^`]*)`', r'\1', s)
    # 图片 ![alt](url) → alt
    s = re.sub(r'!\[([^\]]*)\]\([^)]*\)', r'\1', s)
    # 链接 [text](url) → text
    s = re.sub(r'\[([^\]]*)\]\([^)]*\)', r'\1', s)
    # 标题 # ## ### → 去掉 # 号
    s = re.sub(r'^#{1,6}\s+', '', s, flags=re.MULTILINE)
    # 加粗 **text** 或 __text__
    s = re.sub(r'\*\*(.+?)\*\*', r'\1', s)
    s = re.sub(r'__(.+?)__', r'\1', s)
    # 斜体 *text* 或 _text_
    s = re.sub(r'\*(.+?)\*', r'\1', s)
    s = re.sub(r'(?<!\w)_(.+?)_(?!\w)', r'\1', s)
    # 删除线 ~~text~~
    s = re.sub(r'~~(.+?)~~', r'\1', s)
    # 引用 > text
    s = re.sub(r'^>\s?', '', s, flags=re.MULTILINE)
    # 无序列表 - / * / +
    s = re.sub(r'^[\s]*[-*+]\s+', '', s, flags=re.MULTILINE)
    # 有序列表 1. 2.
    s = re.sub(r'^[\s]*\d+\.\s+', '', s, flags=re.MULTILINE)
    # 水平线 --- 或 *** 或 ___
    s = re.sub(r'^[-*_]{3,}\s*$', '', s, flags=re.MULTILINE)
    # 表格 | --- | --- |
    s = re.sub(r'\|[\s\-:]+\|', '', s)
    # 表格行 | text | text |
    s = re.sub(r'\|', ' ', s)
    # HTML 标签
    s = re.sub(r'<[^>]+>', '', s)
    # 多余空行
    s = re.sub(r'\n{3,}', '\n\n', s)
    # 去掉所有标点符号和特殊字符（TTS 不读）
    s = re.sub(r'[，。！？；：、""''【】（）《》\-—…·「」『』〈〉〔〕｛｝‖｜\n]', ' ', s)
    s = re.sub(r'[,.!?;:\'"()\[\]{}<>/\\@#$%^&*+=_~`|]', ' ', s)
    # 多余空格
    s = re.sub(r'\s+', ' ', s).strip()
    return s


# ── 显示器控制意图识别 ───────────────────────────────────────────
def parse_voice_command(text):
    """将用户语音文字解析为显示器控制命令，返回 dict 或 None"""
    if not text:
        return None
    t = text.lower().strip()

    # ── 亮度 ──
    m = re.search(r'(?:把\s*)?亮度\s*(?:调|设)(?:成|为|到|整?到)?\s*(\d{1,3})%?', t)
    if not m:
        m = re.search(r'(?:亮度|屏幕)\s*[:：]?\s*(\d{1,3})%?', t)
    if m:
        return {"action": "set", "control": "brightness", "value": int(m.group(1))}

    if re.search(r'(?:亮度|屏幕)\s*(?:调|设)?(?:成|为|到)?\s*(?:最高|最大|最亮|full)', t):
        return {"action": "set", "control": "brightness", "value": 100}
    if re.search(r'(?:亮度|屏幕)\s*(?:调|设)?(?:成|为|到)?\s*(?:最低|最小|最暗)', t):
        return {"action": "set", "control": "brightness", "value": 0}
    # 带数值的相对调整："亮度调高40" → delta +40
    m = re.search(r'(?:亮度|屏幕)\s*(?:调|设)?(?:高|大|亮)\s*(\d{1,3})', t)
    if m:
        return {"action": "adjust", "control": "brightness", "delta": int(m.group(1))}
    m = re.search(r'(?:亮度|屏幕)\s*(?:调|设)?(?:低|小|暗)\s*(\d{1,3})', t)
    if m:
        return {"action": "adjust", "control": "brightness", "delta": -int(m.group(1))}
    if re.search(r'(?:亮度|屏幕|显示器).*(?:增高|调高|提高|升高|增加|加大|亮一点|更亮|变亮|再亮点|稍微亮点|亮一些|稍亮点|调亮一点)', t):
        return {"action": "adjust", "control": "brightness", "delta": 10}
    if re.search(r'(?:亮度|屏幕|显示器).*(?:调低|降低|减小|减弱|减少|暗一点|更暗|变暗|再暗点|稍微暗点|暗一些|稍暗点|调暗一点)', t):
        return {"action": "adjust", "control": "brightness", "delta": -10}

    # ── 对比度 ──
    m = re.search(r'(?:把\s*)?对比度\s*(?:调|设)(?:成|为|到|整?到)?\s*(\d{1,3})%?', t)
    if m:
        return {"action": "set", "control": "contrast", "value": int(m.group(1))}

    if re.search(r'对比度\s*(?:调|设)?(?:成|为|到)?\s*(?:最高|最大)', t):
        return {"action": "set", "control": "contrast", "value": 100}
    if re.search(r'对比度\s*(?:调|设)?(?:成|为|到)?\s*(?:最低|最小)', t):
        return {"action": "set", "control": "contrast", "value": 0}
    m = re.search(r'对比度\s*(?:调|设)?(?:高|大)\s*(\d{1,3})', t)
    if m:
        return {"action": "adjust", "control": "contrast", "delta": int(m.group(1))}
    m = re.search(r'对比度\s*(?:调|设)?(?:低|小)\s*(\d{1,3})', t)
    if m:
        return {"action": "adjust", "control": "contrast", "delta": -int(m.group(1))}
    if re.search(r'对比度.*(?:增高|调高|提高|升高|增加|加大|增大|调大|高一点|高一些)', t):
        return {"action": "adjust", "control": "contrast", "delta": 10}
    if re.search(r'对比度.*(?:调低|降低|减小|减弱|减少|低一点|低一些)', t):
        return {"action": "adjust", "control": "contrast", "delta": -10}

    # ── 音量 ──
    m = re.search(r'(?:把\s*)?音量\s*(?:调|设)(?:成|为|到)?\s*(\d{1,3})%?', t)
    if m:
        return {"action": "set", "control": "volume", "value": int(m.group(1))}

    if re.search(r'音量.*(?:最高|最大|全开)', t):
        return {"action": "set", "control": "volume", "value": 100}
    if re.search(r'(?:静音|mute)', t) or re.search(r'音量.*(?:最低|最小|关掉)', t):
        return {"action": "set", "control": "volume", "value": 0}
    m = re.search(r'音量\s*(?:调|设)?(?:高|大)\s*(\d{1,3})', t)
    if m:
        return {"action": "adjust", "control": "volume", "delta": int(m.group(1))}
    m = re.search(r'音量\s*(?:调|设)?(?:低|小)\s*(\d{1,3})', t)
    if m:
        return {"action": "adjust", "control": "volume", "delta": -int(m.group(1))}
    if re.search(r'音量.*(?:增高|调高|提高|升高|增加|加大|大一点|大声点|声音大点|声音大一些|音量增大|声音变大|增大|变大)|声音(?:大一点|大些|变大)', t):
        return {"action": "adjust", "control": "volume", "delta": 10}
    if re.search(r'音量.*(?:调低|降低|减小|减弱|减少|小一点|小声点|声音小点|声音小一些|音量减小|声音变小|减小|变小)|声音(?:小一点|小些|变小|减少|减小)', t):
        return {"action": "adjust", "control": "volume", "delta": -10}

    return None


# ── 状态 ─────────────────────────────────────────────────────────
class PipelineState:
    IDLE = "idle"                   # 麦克风热，VAD 监听
    WAKE_LISTEN = "wake_listen"     # 语音触发，检查唤醒词
    COMMAND_LISTEN = "command_listen"  # 唤醒词确认，缓冲指令
    PROCESSING = "processing"       # ASR + LLM 运行中
    SPEAKING = "speaking"           # TTS 播放中
    PAUSED = "paused"              # 用户暂停


# ── 管线 ─────────────────────────────────────────────────────────
class VoicePipeline(QObject):
    # Qt 信号（跨线程安全）
    state_changed = Signal(str)         # 新状态名
    wake_word_detected = Signal(str)    # 唤醒词文本
    command_captured = Signal(str)      # ASR 识别出的指令文本
    ai_response_stream = Signal(str)    # LLM 流式 token（累积全文）
    ai_response_done = Signal(str)      # LLM 最终完整回复
    tts_start = Signal()                # TTS 开始播放
    tts_done = Signal()                 # TTS 播放完成
    error_occurred = Signal(str)        # 错误信息

    def __init__(self, wake_word="小助手", server_url="http://127.0.0.1:18766",
                 vad_threshold=0.5, wake_threshold=0.5, silence_timeout_ms=700,
                 parent=None):
        super().__init__(parent)
        self._wake_word = wake_word
        self._server_url = server_url
        self._vad_threshold = vad_threshold
        self._wake_threshold = wake_threshold
        self._silence_timeout_ms = silence_timeout_ms
        self._wake_listen_silence_ms = 3000  # WAKE_LISTEN 用更长的静音超时
        self._wake_listen_max_ms = 30000     # WAKE_LISTEN 最大时长（30秒）
        self._wake_listen_start_ts = 0       # WAKE_LISTEN 开始时间戳

        # 状态
        self._state = PipelineState.IDLE
        self._paused = False

        # 音频参数
        self._sample_rate = 16000
        self._chunk_size = 512  # 32ms per chunk

        # 模型
        self._vad_model = None
        self._oww_model = None

        # 音频缓冲
        self._audio_deque = collections.deque(maxlen=100)  # ~3.2s buffer
        self._speech_buffer = bytearray()
        self._silence_frames = 0
        self._last_wake_check_ts = 0  # 上次唤醒词检查时间戳

        # 线程
        self._audio_thread = None
        self._worker_thread = None
        self._running = False
        self._stream = None

        # 实时 TTS 架构：双队列 + 双线程
        self._sentence_queue = collections.deque()  # 文本队列
        self._audio_queue = collections.deque()     # 音频队列
        self._tts_thread = None                     # TTS 工作线程
        self._player_thread = None                  # 音频播放线程
        self._tts_running = False                   # TTS 线程运行标志
        self._player_running = False                # 播放线程运行标志
        self._current_tts_proc = None               # 当前 TTS 进程
        self._current_ffplay_proc = None            # 当前 ffplay 播放进程
        self._interrupted = False                   # 打断标志
        self._tts_generation = 0                    # TTS 代次（防旧线程干扰新线程）
        self._tts_muted = False                     # 禁止自动朗读
        self._mic_device = None                     # 麦克风设备（None=默认）
        self._model = "qwen3-vl:4b"                # LLM 模型名称

    # ── 公开方法 ─────────────────────────────────────────────────
    def start(self):
        """启动管线（后台线程加载模型并开始监听）"""
        if self._running:
            return
        self._running = True
        self._paused = False
        self._audio_thread = threading.Thread(target=self._audio_loop, daemon=True)
        self._audio_thread.start()

    def stop(self):
        """停止管线"""
        self._running = False
        self._interrupt()
        self._set_state(PipelineState.IDLE)

    def pause(self):
        """暂停监听"""
        self._paused = True
        self._set_state(PipelineState.PAUSED)

    def resume(self):
        """恢复监听"""
        self._paused = False
        self._set_state(PipelineState.IDLE)

    def notify_tts_start(self):
        """TTS 开始播放，管线静音"""
        self._set_state(PipelineState.SPEAKING)
        self.tts_start.emit()

    def notify_tts_done(self):
        """TTS 播放完成，恢复监听"""
        if self._state == PipelineState.SPEAKING:
            self._set_state(PipelineState.IDLE)

    # ── 打断功能 ─────────────────────────────────────────────────
    def _interrupt(self):
        """打断当前 TTS/LLM（非阻塞，立即返回）。不改状态，由调用方负责。"""
        self._interrupted = True
        # 清空队列
        self._sentence_queue.clear()
        self._audio_queue.clear()
        # 停止 TTS 进程
        if self._current_tts_proc and self._current_tts_proc.poll() is None:
            self._current_tts_proc.terminate()
            self._current_tts_proc = None
        # 停止 ffplay 播放进程（Windows 需要 taskkill 确保子进程被杀）
        if self._current_ffplay_proc and self._current_ffplay_proc.poll() is None:
            try:
                subprocess.run(
                    ["taskkill", "/F", "/T", "/PID", str(self._current_ffplay_proc.pid)],
                    capture_output=True, timeout=3
                )
            except Exception:
                try:
                    self._current_ffplay_proc.kill()
                except Exception:
                    pass
            self._current_ffplay_proc = None
        # 设置线程退出标志（非阻塞，线程会自行退出）
        self._tts_running = False
        self._player_running = False
        _flog("[打断] 已打断当前 TTS/LLM")

    # ── 内部方法 ─────────────────────────────────────────────────
    def _set_state(self, state):
        if self._state != state:
            old = self._state
            self._state = state
            _flog(f"[状态] {old} → {state}")
            self.state_changed.emit(state)

    def _load_models(self):
        """加载 VAD 模型"""
        # Silero VAD
        try:
            _flog("[VAD] 加载 Silero VAD 模型...")
            from silero_vad import load_silero_vad
            self._vad_model = load_silero_vad(onnx=True)
            _flog("[VAD] Silero VAD 加载完成")
        except Exception as e:
            _flog(f"[VAD] Silero VAD 加载失败: {e}，使用能量 VAD 回退")
            self._vad_model = None

        # 唤醒词检测使用 ASR 方式，无需额外模型
        _flog("[唤醒] 使用 ASR 方式检测唤醒词")

    def _audio_loop(self):
        """音频采集 + 状态机主循环"""
        # 加载模型
        self._load_models()

        _flog("[音频] 开始麦克风采集")
        self._set_state(PipelineState.IDLE)

        try:
            mic_dev = int(self._mic_device) if self._mic_device else None
            self._stream = sd.InputStream(
                samplerate=self._sample_rate,
                channels=1,
                dtype='int16',
                blocksize=self._chunk_size,
                device=mic_dev,
                callback=self._audio_callback,
            )
            self._stream.start()
        except Exception as e:
            _flog(f"[音频] 麦克风打开失败: {e}")
            self.error_occurred.emit(f"麦克风不可用: {e}")
            self._set_state(PipelineState.PAUSED)
            return

        # 主循环：从 deque 读取音频块并处理
        while self._running:
            try:
                if not self._audio_deque:
                    time.sleep(0.01)
                    continue

                chunk = self._audio_deque.popleft()  # int16 numpy array
                self._process_chunk(chunk)

            except Exception as e:
                _flog(f"[音频] 处理异常: {e}")
                time.sleep(0.1)

        # 清理
        try:
            self._stream.stop()
            self._stream.close()
        except Exception:
            pass
        _flog("[音频] 麦克风已关闭")

    def _audio_callback(self, indata, frames, time_info, status):
        """sounddevice 回调：推入 deque"""
        if self._running:
            self._audio_deque.append(indata[:, 0].copy())

    def _process_chunk(self, chunk):
        """处理单个音频块，驱动状态机"""
        state = self._state

        # 暂停或处理中：忽略音频
        if state in (PipelineState.PAUSED, PipelineState.PROCESSING):
            return

        # SPEAKING 状态：高阈值检测语音（过滤扬声器 TTS 回声）
        if state == PipelineState.SPEAKING:
            vad_prob = self._get_vad_prob(chunk)
            if vad_prob >= 0.8:  # 高阈值，过滤 TTS 扬声器回声
                _flog(f"[VAD] SPEAKING 中检测到语音 prob={vad_prob:.2f}，打断并进入指令监听")
                # 立即打断 TTS 播放
                self._interrupt()
                # 打断后直接进入 COMMAND_LISTEN（不需要再检测唤醒词）
                self._speech_buffer = bytearray()
                self._silence_frames = 0
                self._append_to_buffer(chunk)
                self._set_state(PipelineState.COMMAND_LISTEN)
            return

        # 计算 VAD 概率
        vad_prob = self._get_vad_prob(chunk)

        if state == PipelineState.IDLE:
            if vad_prob >= self._vad_threshold:
                _flog(f"[VAD] 检测到语音 prob={vad_prob:.2f}")
                self._speech_buffer = bytearray()
                self._silence_frames = 0
                self._last_wake_check_ts = 0
                self._wake_listen_start_ts = time.time()
                self._append_to_buffer(chunk)
                self._set_state(PipelineState.WAKE_LISTEN)

        elif state == PipelineState.WAKE_LISTEN:
            self._append_to_buffer(chunk)

            if vad_prob >= self._vad_threshold:
                self._silence_frames = 0
            else:
                self._silence_frames += 1

            # 检查唤醒词（积累 ~1.5 秒音频后，每 ~500ms 检查一次）
            min_bytes = int(self._sample_rate * 1.5 * 2)  # 1.5 秒的 int16 数据
            now = time.time()
            if len(self._speech_buffer) >= min_bytes and (now - self._last_wake_check_ts) >= 0.5:
                self._last_wake_check_ts = now
                if self._check_wake_word():
                    _flog(f"[唤醒] 唤醒词命中: {self._wake_word}")
                    # 打断当前 TTS/LLM
                    self._interrupt()
                    self.wake_word_detected.emit(self._wake_word)
                    # 保留已缓冲的音频（唤醒词后面的可能是指令）
                    self._silence_frames = 0
                    self._set_state(PipelineState.COMMAND_LISTEN)
                    return
                else:
                    # 唤醒词未命中，清理旧缓冲（保留最近 1.5 秒）
                    max_keep = int(self._sample_rate * 1.5 * 2)
                    if len(self._speech_buffer) > max_keep * 2:
                        self._speech_buffer = self._speech_buffer[-max_keep:]

            # 静音超时：无唤醒词，回退到 IDLE（WAKE_LISTEN 用更长超时）
            silence_ms = self._silence_frames * (self._chunk_size / self._sample_rate * 1000)
            if silence_ms >= self._wake_listen_silence_ms:
                _flog(f"[唤醒] 静音超时 {silence_ms:.0f}ms，无唤醒词")
                self._speech_buffer = bytearray()
                self._set_state(PipelineState.IDLE)
                return

            # 最大时长超时：防止无限卡在 WAKE_LISTEN
            listen_ms = (now - self._wake_listen_start_ts) * 1000
            if listen_ms >= self._wake_listen_max_ms:
                _flog(f"[唤醒] 最大监听时长 {listen_ms:.0f}ms，无唤醒词，回退 IDLE")
                self._speech_buffer = bytearray()
                self._set_state(PipelineState.IDLE)

        elif state == PipelineState.COMMAND_LISTEN:
            self._append_to_buffer(chunk)

            if vad_prob >= self._vad_threshold:
                self._silence_frames = 0
            else:
                self._silence_frames += 1

            # 静音超时：指令结束
            if self._silence_frames * (self._chunk_size / self._sample_rate * 1000) >= self._silence_timeout_ms:
                _flog(f"[指令] 静音超时，缓冲 {len(self._speech_buffer)} bytes")
                # 截取唤醒词之后的音频作为指令
                command_audio = bytes(self._speech_buffer)
                self._speech_buffer = bytearray()
                self._set_state(PipelineState.PROCESSING)
                # 在 worker 线程中处理 ASR + LLM
                self._worker_thread = threading.Thread(
                    target=self._process_command, args=(command_audio,), daemon=True
                )
                self._worker_thread.start()

    def _get_vad_prob(self, chunk):
        """获取 VAD 语音概率"""
        if self._vad_model is not None:
            try:
                import torch
                audio_float = chunk.astype(np.float32) / 32768.0
                tensor = torch.from_numpy(audio_float)
                prob = self._vad_model(tensor, self._sample_rate).item()
                return prob
            except Exception as e:
                _flog(f"[VAD] 推理异常: {e}")
                return 0.0
        else:
            # 回退：简单能量 VAD
            rms = np.sqrt(np.mean(chunk.astype(np.float32) ** 2)) / 32768.0
            return min(rms * 10, 1.0)

    def _append_to_buffer(self, chunk):
        """将 chunk 追加到语音缓冲"""
        self._speech_buffer.extend(chunk.tobytes())

    def _check_wake_word(self):
        """检查缓冲音频中是否包含唤醒词（ASR 方式）"""
        if len(self._speech_buffer) < self._sample_rate * 2:  # 至少 1 秒
            return False

        try:
            # 将缓冲的 PCM 转为 webm 发送到 ASR
            pcm_data = bytes(self._speech_buffer)
            webm_file = os.path.join(tempfile.gettempdir(), f"wake_{uuid.uuid4().hex}.webm")
            proc = subprocess.run(
                ["ffmpeg", "-y", "-f", "s16le", "-ar", str(self._sample_rate), "-ac", "1",
                 "-i", "pipe:0", "-c:a", "libopus", "-b:a", "32k", webm_file],
                input=pcm_data, capture_output=True, timeout=5
            )
            if proc.returncode != 0:
                return False

            # 发送到 ASR
            text = self._transcribe(webm_file)
            try:
                os.unlink(webm_file)
            except Exception:
                pass

            if not text:
                return False

            _flog(f"[唤醒] ASR 结果: {text}")

            # 检查是否以唤醒词开头
            text_lower = text.lower().strip()
            wake_lower = self._wake_word.lower()
            if text_lower.startswith(wake_lower):
                return True

            # 也检查是否包含唤醒词（更宽松）
            if wake_lower in text_lower:
                return True

            # ASR 可能漏掉"小"字，回退检查"助手"
            if wake_lower.startswith("小") and "助手" in text_lower:
                _flog(f"[唤醒] 回退匹配'助手'")
                return True

            return False

        except Exception as e:
            _flog(f"[唤醒] ASR 检测异常: {e}")
            return False

    def _process_command(self, pcm_data):
        """Worker 线程：ASR + LLM + 实时 TTS"""
        try:
            # 1. PCM → webm
            webm_file = os.path.join(tempfile.gettempdir(), f"cmd_{uuid.uuid4().hex}.webm")
            proc = subprocess.run(
                ["ffmpeg", "-y", "-f", "s16le", "-ar", str(self._sample_rate), "-ac", "1",
                 "-i", "pipe:0", "-c:a", "libopus", "-b:a", "32k", webm_file],
                input=pcm_data, capture_output=True, timeout=15
            )
            if proc.returncode != 0:
                _flog(f"[ASR] ffmpeg 错误: {proc.stderr.decode('utf-8', errors='replace')[:200]}")
                self.error_occurred.emit("音频转码失败")
                self._set_state(PipelineState.IDLE)
                return

            # 2. ASR
            _flog(f"[ASR] 发送到 SenseVoice...")
            text = self._transcribe(webm_file)
            try:
                os.unlink(webm_file)
            except Exception:
                pass

            if not text:
                _flog("[ASR] 无识别结果")
                self.error_occurred.emit("语音识别无结果")
                self._set_state(PipelineState.IDLE)
                return

            _flog(f"[ASR] 识别结果: {text}")
            # 去掉开头的唤醒词
            text_lower = text.lower().strip()
            wake_lower = self._wake_word.lower()
            if text_lower.startswith(wake_lower):
                text = text[len(self._wake_word):].strip()
            elif wake_lower in text_lower:
                idx = text_lower.index(wake_lower)
                text = (text[:idx] + text[idx + len(self._wake_word):]).strip()
            _flog(f"[ASR] 去掉唤醒词后: {text}")
            self.command_captured.emit(text)

            # 3. 意图识别：Regex → LLM
            intents = None
            intent = parse_voice_command(text)
            if intent:
                intents = [intent]
            else:
                intents = self._llm_intent_detect(text)
            if intents:
                _flog(f"[意图] 命中显示器控制: {intents}")
                replies = []
                for it in intents:
                    reply = self._execute_display_control(it)
                    replies.append(reply)
                full_reply = "，".join(replies)
                self.ai_response_stream.emit(full_reply)
                self.ai_response_done.emit(full_reply)
                # TTS 播放回复（检查是否静音）
                if not self._tts_muted:
                    self._interrupted = False
                    self.notify_tts_start()
                    self._start_tts_workers()
                    clean = _strip_md(full_reply)
                    if clean:
                        self._sentence_queue.append(clean)
                    self._sentence_queue.append(None)
                else:
                    self._set_state(PipelineState.IDLE)
                return

            # 4. 启动实时 TTS 架构
            if not self._tts_muted:
                self._interrupted = False
                self.notify_tts_start()
                self._start_tts_workers()  # 状态 → speaking + 通知 UI

            # 5. LLM 流式生成 + 实时分句
            self._stream_llm_with_tts(text)

        except Exception as e:
            _flog(f"[处理] 异常: {e}")
            self.error_occurred.emit(str(e))
            self._set_state(PipelineState.IDLE)

    def _http_get_json(self, path):
        """GET 请求 server 端点，返回 JSON dict"""
        url = self._server_url + path
        try:
            resp = urlopen(url, timeout=5)
            return json.loads(resp.read().decode("utf-8"))
        except Exception as e:
            _flog(f"[HTTP] GET {path} 失败: {e}")
            return None

    def _http_post_json(self, path, data):
        """POST 请求 server 端点，返回 JSON dict"""
        url = self._server_url + path
        try:
            payload = json.dumps(data).encode()
            req = Request(url, data=payload,
                          headers={"Content-Type": "application/json"}, method="POST")
            resp = urlopen(req, timeout=5)
            return json.loads(resp.read().decode("utf-8"))
        except Exception as e:
            _flog(f"[HTTP] POST {path} 失败: {e}")
            return None

    def _execute_display_control(self, intent):
        """执行显示器控制命令，返回 TTS 回复文字"""
        action = intent["action"]
        control = intent["control"]

        # 读取 displayType
        dt_resp = self._http_get_json("/config/displayType")
        display_type = (dt_resp or {}).get("displayType", "native")

        # 对比度需要 DDC/CI 支持
        if control == "contrast" and display_type != "adb":
            return "您好，当前显示器不支持DDC/CI，无法调节对比度。"

        # 确定端点前缀
        if control == "volume":
            prefix = "/native"
        elif display_type == "adb":
            prefix = "/ddcci"
        else:
            prefix = "/native"

        # 获取当前值（adjust 时需要）
        current = None
        if action == "adjust":
            if control == "volume":
                # 用 pycaw 读取实际系统音量（缓存可能过期）
                try:
                    from pycaw.pycaw import AudioUtilities
                    speakers = AudioUtilities.GetSpeakers()
                    vol = speakers.EndpointVolume
                    current = int(vol.GetMasterVolumeLevelScalar() * 100)
                    _flog(f"[控制] 实际音量: {current}%")
                except Exception as e:
                    _flog(f"[控制] pycaw 读取失败: {e}，使用缓存")
                    r = self._http_get_json("/native/volume")
                    current = (r or {}).get("volume", 50)
            elif control == "brightness":
                if prefix == "/ddcci":
                    r = self._http_get_json("/ddcci/status")
                    current = (r or {}).get("brightness", 50)
                else:
                    r = self._http_get_json("/native/status")
                    current = (r or {}).get("brightness", 50)
            elif control == "contrast":
                if prefix == "/ddcci":
                    r = self._http_get_json("/ddcci/contrast_read")
                    current = (r or {}).get("value", 50)
                else:
                    r = self._http_get_json("/native/status")
                    current = (r or {}).get("contrast", 50)

        # 计算目标值
        if action == "set":
            value = intent["value"]
        else:  # adjust
            base = current if current is not None else 50
            value = max(0, min(100, base + intent["delta"]))

        # 执行
        endpoint = f"{prefix}/{control}"
        result = self._http_post_json(endpoint, {"value": value})
        _flog(f"[控制] {control} → {value} (displayType={display_type})")

        # 构造 TTS 回复
        ctrl_name = {"brightness": "亮度", "contrast": "对比度", "volume": "音量"}.get(control, control)
        reply = f"好的，已将{ctrl_name}设为{value}%"
        return reply

    def _llm_intent_detect(self, text):
        """用 LLM 判断文本是否包含显示器控制意图（含语义理解，支持复合意图）"""
        try:
            prompt = (
                "你是显示器控制意图识别器。判断用户的话是否包含亮度、音量、对比度控制意图。\n\n"
                "规则：\n"
                "- \"调到/设为/调成\" + 数字 → action=set, value=数字（绝对值）\n"
                "- \"调高/调低/调大/调小\" + 数字 → action=adjust, delta=±数字（相对值）\n"
                "- \"调高/调大/亮一点\"（无数字）→ action=adjust, delta=±10\n"
                "- \"最亮/最暗/最大/最小/静音\" → action=set, value=极值\n\n"
                "语义理解（重要）：\n"
                "- \"刺眼/晃眼/亮瞎/闪瞎/眼睛疼/太高/高了\" → 亮度过高，adjust brightness -15\n"
                "- \"太暗/看不清/黑乎乎/比较低/低了/暗了\" → 亮度过低，adjust brightness +15\n"
                "- \"太吵/炸耳朵/震耳朵/太大声\" → 音量过高，adjust volume -15\n"
                "- \"听不清/听不见/太小声/比较低/小了\" → 音量过低，adjust volume +15\n"
                "- \"闭嘴/安静/别吵了\" → 静音，set volume 0\n"
                "- \"晚上眼睛受不了\" → 亮度过高，adjust brightness -15\n"
                "- 涉及\"屏幕/显示器/亮度/音量/声音/对比度\"的抱怨或请求都算控制意图\n\n"
                "复合意图：用户可能同时提到多个控制项，返回JSON数组。\n\n"
                "输出格式：\n"
                "单个意图：{\"action\":\"adjust\",\"control\":\"brightness\",\"delta\":15}\n"
                "多个意图：[{\"action\":\"adjust\",\"control\":\"brightness\",\"delta\":15},{\"action\":\"adjust\",\"control\":\"volume\",\"delta\":15}]\n"
                "没有控制意图：null\n"
                "只输出JSON或null，不解释。\n\n"
                f"用户：{text}"
            )
            payload = json.dumps({
                "model": self._model,
                "messages": [{"role": "user", "content": prompt}],
                "stream": False
            }).encode()
            req = Request(f"{self._server_url}/ollama/api/chat",
                          data=payload,
                          headers={"Content-Type": "application/json"},
                          method="POST")
            resp = urlopen(req, timeout=30)
            data = json.loads(resp.read().decode("utf-8"))
            content = (data.get("message", {}) or {}).get("content", "").strip()
            _flog(f"[意图LLM] 原始返回: {content}")

            # 清理 think 标签
            if "```" in content:
                m = re.search(r'```(?:json)?\s*([\s\S]*?)```', content)
                if m:
                    content = m.group(1).strip()
            elif ">" in content and "{" in content:
                m = re.search(r'(\{[\s\S]*\})', content)
                if m:
                    content = m.group(1).strip()

            if content.lower() in ("null", "none", ""):
                return None

            parsed = json.loads(content)
            # 支持单个意图或多个意图
            if isinstance(parsed, dict) and "control" in parsed and "action" in parsed:
                _flog(f"[意图LLM] 命中: {[parsed]}")
                return [parsed]
            elif isinstance(parsed, list):
                intents = [i for i in parsed if isinstance(i, dict) and "control" in i and "action" in i]
                if intents:
                    _flog(f"[意图LLM] 命中: {intents}")
                    return intents
            return None
        except Exception as e:
            _flog(f"[意图LLM] 异常: {e}")
            return None

    def _start_tts_workers(self):
        """启动 TTS 工作线程和音频播放线程"""
        # 递增代次（旧线程看到代次不匹配会自行退出）
        self._tts_generation += 1
        # 清空队列
        self._sentence_queue.clear()
        self._audio_queue.clear()

        # 启动 TTS 工作线程
        self._tts_running = True
        self._tts_thread = threading.Thread(target=self._tts_worker, daemon=True)
        self._tts_thread.start()

        # 启动音频播放线程
        self._player_running = True
        self._player_thread = threading.Thread(target=self._audio_player, daemon=True)
        self._player_thread.start()

    def _stop_tts_workers(self):
        """停止 TTS 工作线程和音频播放线程（非阻塞）"""
        self._tts_running = False
        self._player_running = False
        # 清空队列（线程会因标志退出）
        self._sentence_queue.clear()
        self._audio_queue.clear()

    def _drain_audio_queue(self):
        """清空音频队列中剩余的临时文件"""
        while self._audio_queue:
            item = self._audio_queue.popleft()
            if item and isinstance(item, str) and os.path.exists(item):
                try:
                    os.unlink(item)
                except Exception:
                    pass

    def _tts_worker(self):
        """TTS 工作线程：从 Sentence Queue 取句子，生成音频，放入 Audio Queue"""
        gen = self._tts_generation
        _flog(f"[TTS Worker] 启动 gen={gen}")
        while self._tts_running:
            try:
                # 代次不匹配时退出（新 TTS 已启动）
                if gen != self._tts_generation:
                    _flog(f"[TTS Worker] 代次不匹配 (self={gen}, current={self._tts_generation})，退出")
                    break

                # 从队列取句子
                if not self._sentence_queue:
                    time.sleep(0.05)
                    continue

                sentence = self._sentence_queue.popleft()
                if sentence is None:  # 结束信号
                    _flog("[TTS Worker] 收到结束信号")
                    # 放入 None 到音频队列表示结束
                    self._audio_queue.append(None)
                    break

                if self._interrupted:
                    _flog("[TTS Worker] 被打断，跳过句子")
                    continue

                _flog(f"[TTS Worker] 处理句子: {sentence[:30]}...")
                # 调用 TTS 生成音频
                audio_data = self._generate_tts(sentence)
                if audio_data and not self._interrupted:
                    self._audio_queue.append(audio_data)
                    _flog(f"[TTS Worker] 音频已放入队列: {len(audio_data)} bytes")

            except Exception as e:
                _flog(f"[TTS Worker] 异常: {e}")
                time.sleep(0.1)

        _flog("[TTS Worker] 停止")

    def _audio_player(self):
        """音频播放线程：从 Audio Queue 取音频，播放"""
        gen = self._tts_generation  # 启动时的代次
        _flog(f"[Audio Player] 启动 gen={gen}")
        while self._player_running:
            try:
                # 代次不匹配时退出（新 TTS 已启动）
                if gen != self._tts_generation:
                    _flog(f"[Audio Player] 代次不匹配 (self={gen}, current={self._tts_generation})，退出")
                    break

                # 打断时立即退出
                if self._interrupted:
                    _flog("[Audio Player] 被打断，退出")
                    self._drain_audio_queue()
                    break

                # 状态已不是 speaking 时退出
                if self._state != PipelineState.SPEAKING:
                    _flog(f"[Audio Player] 状态已变为 {self._state}，退出")
                    self._drain_audio_queue()
                    break

                # 从队列取音频
                if not self._audio_queue:
                    time.sleep(0.05)
                    continue

                audio_data = self._audio_queue.popleft()
                if audio_data is None:  # 结束信号
                    _flog("[Audio Player] 收到结束信号")
                    break

                # 再次检查打断标志（pop 后可能已被打断）
                if self._interrupted:
                    self._cleanup_audio_file(audio_data)
                    self._drain_audio_queue()
                    break

                _flog(f"[Audio Player] 播放音频: {len(audio_data)} bytes")
                finished = self._play_audio(audio_data)
                if not finished:
                    self._drain_audio_queue()
                    break

            except Exception as e:
                _flog(f"[Audio Player] 异常: {e}")
                time.sleep(0.1)

        _flog(f"[Audio Player] 停止 gen={gen}")
        # 只有当前代次才通知 UI（防止旧线程干扰新线程）
        if gen == self._tts_generation:
            self.tts_done.emit()
            if not self._interrupted:
                self._set_state(PipelineState.IDLE)

    def _generate_tts(self, text):
        """调用 TTS 生成音频，返回音频文件路径"""
        try:
            # 使用 edge-tts 生成音频
            import edge_tts

            mp3_file = os.path.join(tempfile.gettempdir(), f"tts_{uuid.uuid4().hex}.mp3")

            # edge-tts 流式写入文件
            async def _stream():
                comm = edge_tts.Communicate(text, "zh-CN-XiaoxiaoNeural")
                with open(mp3_file, "wb") as f:
                    async for chunk in comm.stream():
                        if chunk["type"] == "audio" and chunk["data"]:
                            f.write(chunk["data"])

            import asyncio
            asyncio.run(_stream())

            if not os.path.exists(mp3_file) or os.path.getsize(mp3_file) == 0:
                _flog("[TTS] 生成的音频文件为空")
                return None

            return mp3_file

        except Exception as e:
            _flog(f"[TTS] 生成异常: {e}")
            return None

    def _play_audio(self, audio_file):
        """播放音频文件，返回 True 表示正常播完，False 表示被打断"""
        try:
            # 打断检查
            if self._interrupted:
                self._cleanup_audio_file(audio_file)
                return False

            # 使用 ffplay 播放
            proc = subprocess.Popen(
                ["ffplay", "-nodisp", "-autoexit", "-loglevel", "quiet", audio_file],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            )
            self._current_ffplay_proc = proc

            # 轮询等待进程结束，每 100ms 检查打断标志
            while proc.poll() is None:
                if self._interrupted:
                    _flog("[Audio Player] 播放被中断，终止 ffplay")
                    try:
                        subprocess.run(
                            ["taskkill", "/F", "/T", "/PID", str(proc.pid)],
                            capture_output=True, timeout=3
                        )
                    except Exception:
                        try:
                            proc.kill()
                        except Exception:
                            pass
                    self._current_ffplay_proc = None
                    self._cleanup_audio_file(audio_file)
                    return False
                time.sleep(0.1)

            self._current_ffplay_proc = None
            self._cleanup_audio_file(audio_file)

            if self._interrupted:
                return False
            return True

        except Exception as e:
            _flog(f"[Audio Player] 播放异常: {e}")
            return False

    def _cleanup_audio_file(self, path):
        try:
            if path and os.path.exists(path):
                os.unlink(path)
        except Exception:
            pass

    def _stream_llm_with_tts(self, text):
        """流式请求 LLM，边生成边分句到 TTS"""
        try:
            # 预检
            try:
                pre = Request(f"{self._server_url}/ollama/api/tags",
                              headers={"Content-Type": "application/json"})
                urlopen(pre, timeout=3).close()
            except Exception as e:
                _flog(f"[LLM] 预检失败: {e}")
                self.error_occurred.emit(f"AI 服务不可达: {e}")
                self._stop_tts_workers()
                self._set_state(PipelineState.IDLE)
                return

            payload = json.dumps({
                "model": self._model,
                "messages": [{"role": "user", "content": text}],
                "stream": True
            }).encode()

            req = Request(f"{self._server_url}/ollama/api/chat",
                          data=payload,
                          headers={"Content-Type": "application/json"},
                          method="POST")
            resp = urlopen(req, timeout=90)

            full = ""
            buf = b""
            token_count = 0
            sentence_buffer = ""
            sentence_end_chars = set("。！？；\n.!?;")

            while not self._interrupted:
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

                            # 每 5 个 token emit 一次流式更新
                            if token_count % 5 == 0 or token_count == 1:
                                self.ai_response_stream.emit(full)

                            # 检查是否句子结束
                            if token and token[-1] in sentence_end_chars:
                                sentence = sentence_buffer.strip()
                                if sentence:
                                    # 清理标点符号
                                    clean_sentence = _strip_md(sentence)
                                    if clean_sentence:
                                        _flog(f"[LLM] 句子完成: {clean_sentence[:30]}...")
                                        self._sentence_queue.append(clean_sentence)
                                    sentence_buffer = ""

                    except json.JSONDecodeError:
                        continue

            resp.close()

            # 处理剩余的句子缓冲
            if sentence_buffer.strip() and not self._interrupted:
                clean_sentence = _strip_md(sentence_buffer.strip())
                if clean_sentence:
                    self._sentence_queue.append(clean_sentence)

            # 发送结束信号到 TTS 线程
            self._sentence_queue.append(None)

            _flog(f"[LLM] 完成 tokens={token_count} len={len(full)}")
            self.ai_response_done.emit(full)

        except Exception as e:
            _flog(f"[LLM] 错误: {e}")
            self.error_occurred.emit(str(e))
            self._stop_tts_workers()
            self._set_state(PipelineState.IDLE)

    def _transcribe(self, webm_file):
        """上传 webm 到 SenseVoice，返回文本"""
        try:
            boundary = uuid.uuid4().hex
            with open(webm_file, "rb") as f:
                audio_data = f.read()

            body = b""
            body += f"--{boundary}\r\n".encode()
            body += b'Content-Disposition: form-data; name="file"; filename="recording.webm"\r\n'
            body += b"Content-Type: audio/webm\r\n\r\n"
            body += audio_data
            body += b"\r\n"
            body += f"--{boundary}--\r\n".encode()

            url = self._server_url.replace("http://", "").split("/")
            host_port = url[0].split(":")
            host = host_port[0]
            port = int(host_port[1]) if len(host_port) > 1 else 80

            conn = http.client.HTTPConnection(host, port, timeout=30)
            conn.request("POST", "/sensevoice/transcribe", body=body,
                         headers={"Content-Type": f"multipart/form-data; boundary={boundary}"})
            resp = conn.getresponse()
            data = json.loads(resp.read().decode("utf-8"))
            conn.close()

            if data.get("success"):
                return data.get("text", "")
            else:
                _flog(f"[ASR] 错误: {data.get('error', '')[:100]}")
                return ""

        except Exception as e:
            _flog(f"[ASR] 请求异常: {e}")
            return ""
