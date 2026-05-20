#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
常开麦克风语音管线：VAD → 唤醒词检测 → 语音识别 → LLM → TTS（实时流式）
"""
import sys, os, json, time, threading, tempfile, uuid, subprocess, http.client, collections, re
import numpy as np
import sounddevice as sd

from urllib.request import urlopen, Request

# ── Reshade 注入器（延迟导入，打包时不进 EXCLUDES）──────────────────────────
try:
    import reshade_inject.launcher as rdx_inject
    _RESHADE_INJECTOR_AVAILABLE = True
except ImportError:
    _RESHADE_INJECTOR_AVAILABLE = False
    rdx_inject = None
from PySide6.QtCore import QObject, Signal
from utils import _strip_md, _flog as _flog_shared

# ── 日志 ─────────────────────────────────────────────────────────
def _log(msg):
    print(f"[Pipeline] {msg}", file=sys.stderr, flush=True)

def _flog(msg):
    _flog_shared("[Pipeline]", msg)


# ── 显示器控制意图识别 ───────────────────────────────────────────
def parse_voice_command(text):
    """将用户语音文字解析为显示器控制命令，返回 dict 或 None"""
    if not text:
        return None
    t = text.lower().strip()

    # ── 亮度 ──
    # set: "亮度调到50"、"亮度调高到50"、"亮度设为50"
    m = re.search(r'(?:把\s*)?亮度\s*(?:调|设)(?:高|大|亮|低|小|暗)?(?:成|为|到|整?到)\s*(\d{1,3})%?', t)
    if not m:
        m = re.search(r'(?:亮度|屏幕)\s*[:：]?\s*(\d{1,3})%?', t)
    if m:
        return {"action": "set", "control": "brightness", "value": int(m.group(1))}

    if re.search(r'(?:亮度|屏幕)\s*(?:调|设)?(?:成|为|到)?\s*(?:最高|最大|最亮|full)', t):
        return {"action": "set", "control": "brightness", "value": 100}
    if re.search(r'(?:亮度|屏幕)\s*(?:调|设)?(?:成|为|到)?\s*(?:最低|最小|最暗)', t):
        return {"action": "set", "control": "brightness", "value": 0}
    # adjust: "亮度调高40" → delta +40（不含"到"）
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
    m = re.search(r'(?:把\s*)?对比度\s*(?:调|设)(?:高|大|低|小)?(?:成|为|到|整?到)\s*(\d{1,3})%?', t)
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

    # ── 色温 ──
    # set: "色温调到50"、"色温设为60"
    m = re.search(r'(?:把\s*)?色温\s*(?:调|设)(?:高|大|低|小)?(?:成|为|到|整?到)\s*(\d{1,3})%?', t)
    if not m:
        m = re.search(r'色温\s*[:：]?\s*(\d{1,3})%?', t)
    if m:
        return {"action": "set", "control": "color_temp", "value": int(m.group(1))}

    # 色温暖/冷/偏暖/偏冷
    if re.search(r'色温.*(?:最暖|最黄|暖色)', t):
        return {"action": "set", "control": "color_temp", "value": 0}
    if re.search(r'色温.*(?:最冷|最蓝|冷色)', t):
        return {"action": "set", "control": "color_temp", "value": 100}
    if re.search(r'色温.*(?:中性|正常|标准|默认)', t):
        return {"action": "set", "control": "color_temp", "value": 50}

    # adjust: "色温调高30" → delta +30
    m = re.search(r'色温\s*(?:调|设)?(?:高|大|冷)\s*(\d{1,3})', t)
    if m:
        return {"action": "adjust", "control": "color_temp", "delta": int(m.group(1))}
    m = re.search(r'色温\s*(?:调|设)?(?:低|小|暖)\s*(\d{1,3})', t)
    if m:
        return {"action": "adjust", "control": "color_temp", "delta": -int(m.group(1))}

    # 色温偏暖/偏冷（无数字，±10）
    if re.search(r'色温.*(?:调高|提高|升高|冷一点|冷一些|偏冷|再冷)', t):
        return {"action": "adjust", "control": "color_temp", "delta": 10}
    if re.search(r'色温.*(?:调低|降低|暖一点|暖一些|偏暖|再暖|黄一点)', t):
        return {"action": "adjust", "control": "color_temp", "delta": -10}

    # ── 音量 ──
    # set: "音量调到50"、"音量调高到50"、"音量设为50"
    m = re.search(r'(?:把\s*)?音量\s*(?:调|设)(?:高|大|低|小)?(?:成|为|到)\s*(\d{1,3})%?', t)
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


    # ── 一键 HDR ──
    if re.search(r'(?:开启?|启动|打开?|应用?)(?:HDR|hdr|one.?key|一键)', t):
        return {"action": "set", "control": "hdr_onekey", "value": 0}
    if re.search(r'(?:关闭?|停用|禁用)(?:HDR|hdr)', t):
        return {"action": "set", "control": "hdr_off", "value": 0}

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

    def speak_text(self, text):
        """启动 TTS 朗读文本（封装 interrupt → notify → start workers → enqueue）"""
        clean = _strip_md(text)
        if not clean:
            return
        self._interrupted = False
        self.notify_tts_start()
        self._start_tts_workers()
        self._sentence_queue.append(clean)
        self._sentence_queue.append(None)

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
                    capture_output=True, timeout=3,
                    creationflags=subprocess.CREATE_NO_WINDOW,
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
        try:
            _flog("[VAD] 加载 Silero VAD 模型...")
            from vad_engine import SileroVAD
            self._vad_model = SileroVAD()
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
                audio_float = chunk.astype(np.float32) / 32768.0
                prob = self._vad_model(audio_float, self._sample_rate)
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
                input=pcm_data, capture_output=True, timeout=5,
                creationflags=subprocess.CREATE_NO_WINDOW,
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

            # ASR 可能漏字/错字，回退：检查唤醒词的连续子串（至少 2 字）
            for length in range(len(wake_lower), 1, -1):
                for i in range(len(wake_lower) - length + 1):
                    sub = wake_lower[i:i + length]
                    if len(sub) >= 2 and sub in text_lower:
                        _flog(f"[唤醒] 子串匹配'{sub}'")
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
                input=pcm_data, capture_output=True, timeout=15,
                creationflags=subprocess.CREATE_NO_WINDOW,
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
                    self.speak_text(full_reply)
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

    def _count_monitors(self):
        """返回 DDC/CI 物理监视器数量"""
        try:
            r = self._http_get_json("/ddcci/monitor_count")
            if r and r.get("count"):
                return r["count"]
        except Exception:
            pass
        return 1

    @staticmethod
    def _get_system_volume_obj():
        """获取 pycaw 音量对象（确保 COM 已初始化）"""
        import comtypes
        comtypes.CoInitialize()
        from pycaw.pycaw import AudioUtilities
        speakers = AudioUtilities.GetSpeakers()
        return speakers.EndpointVolume

    def _get_system_volume(self):
        """读取系统音量（0~100），失败返回 None"""
        try:
            vol = self._get_system_volume_obj()
            return round(vol.GetMasterVolumeLevelScalar() * 100)
        except Exception as e:
            _flog(f"[音量] 读取失败: {e}")
            return None

    def _set_system_volume(self, value):
        """设置系统音量（0~100），返回实际值，失败返回 None"""
        try:
            vol = self._get_system_volume_obj()
            vol.SetMasterVolumeLevelScalar(value / 100.0, None)
            actual = round(vol.GetMasterVolumeLevelScalar() * 100)
            _flog(f"[音量] 设置 → {actual}%")
            return actual
        except Exception as e:
            _flog(f"[音量] 设置失败: {e}")
            return None

    def _execute_display_control(self, intent):
        """执行显示器控制命令，返回 TTS 回复文字"""
        action = intent["action"]
        control = intent["control"]

        # 读取 displayType
        dt_resp = self._http_get_json("/config/displayType")
        display_type = (dt_resp or {}).get("displayType", "native")

        # 确定端点前缀
        if control == "volume":
            prefix = "/native"
        elif control in ("contrast", "color_temp"):
            # 对比度和色温优先走 DDC/CI（硬件控制），不依赖 displayType 配置
            prefix = "/ddcci"
        elif display_type == "adb":
            prefix = "/ddcci"
        else:
            prefix = "/native"

        # 获取当前值（adjust 时需要）
        current = None
        if action == "adjust":
            if control == "volume":
                current = self._get_system_volume()
                if current is not None:
                    _flog(f"[控制] 实际音量: {current}%")
                else:
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
                r = self._http_get_json("/ddcci/contrast_read")
                current = (r or {}).get("value", 50)
            elif control == "color_temp":
                r = self._http_get_json("/native/status")
                current = (r or {}).get("colorTemp", 50)

        # 计算目标值
        if action == "set":
            value = intent["value"]
        else:  # adjust
            base = current if current is not None else 50
            value = max(0, min(100, base + intent["delta"]))

        # 执行
        mon_name = ""
        if control == "volume":
            actual = self._set_system_volume(value)
            if actual is not None:
                value = actual
            else:
                endpoint = f"{prefix}/{control}"
                self._http_post_json(endpoint, {"value": value})
        else:
            endpoint = f"{prefix}/{control}"
            result = self._http_post_json(endpoint, {"value": value})
        if isinstance(result, dict):
                mon_name = result.get("monitorName", "")
                # DDC/CI 失败时返回提示
                if prefix == "/ddcci" and not result.get("success", True):
                    ctrl_name = {"contrast": "对比度", "color_temp": "色温"}.get(control, control)
                    return f"当前显示器不支持DDC/CI{ctrl_name}调节。"
        _flog(f"[控制] {control} → {value} (displayType={display_type}, monitor='{mon_name}')")

        # ── 一键 HDR：检测游戏 + 渲染管线注入 + OSD 调整 ───────────────
        if control == "hdr_onekey":
            game, addon_info = self._detect_foreground_game()
            is_game = game and game not in ("(系统)", "(应用)", "(终端)", "(资源管理器)",
                                          "(Cortana)", "(设置)", "(Notepad++)", "VS Code",
                                          "Visual Studio", "PyCharm", "IntelliJ IDEA",
                                          "Steam", "Epic", "GOG", "Origin", "Ubisoft")
            if not (is_game or addon_info):
                return "未检测到支持HDR的游戏，请先启动游戏"

            game_name = game or "游戏"
            addon_name = (addon_info or {}).get("addon_name")
            url = (addon_info or {}).get("url")
            exe_path = self._get_foreground_process()
            game_dir = os.path.dirname(exe_path) if exe_path else None
            hdr = (addon_info or {}).get("hdr_values") or {"brightness": 80, "contrast": 75, "color_temp": 55}

            # 1. 下载 addon 到游戏目录
            if game_dir and addon_name and url:
                dest = os.path.join(game_dir, addon_name)
                if not os.path.exists(dest):
                    try:
                        import ssl as _ssl
                        ctx = _ssl.create_default_context()
                        ctx.check_hostname = False
                        ctx.verify_mode = _ssl.CERT_NONE
                        data = urllib.request.urlopen(url, timeout=30, context=ctx).read()
                        with open(dest, "wb") as f:
                            f.write(data)
                        _flog(f"[HDR] addon 已下载: {addon_name} ({len(data)//1024} KB)")
                    except Exception as e:
                        _flog(f"[HDR] addon 下载失败: {e}")

            # 2. 渲染管线注入（若注入器可用）
            injected = False
            if _RESHADE_INJECTOR_AVAILABLE and addon_info:
                pid = self._get_foreground_pid()
                if pid and game_dir and addon_name:
                    try:
                        inj = rdx_inject.ReshadeInjector(game_dir)
                        addon_abs = os.path.join(game_dir, addon_name)
                        injected = inj.inject(pid, addon_abs)
                        _flog(f"[HDR] 渲染管线注入{'成功' if injected else '失败'}")
                    except Exception as e:
                        _flog(f"[HDR] 注入异常: {e}")

            # 3. OSD 调整
            for ctrl, val in hdr.items():
                self._http_post_json(f"/ddcci/{ctrl}", {"value": val})

            # 4. 合成回复
            mon_count = self._count_monitors()
            if mon_count > 1:
                r = self._http_get_json("/ddcci/status")
                mon_name = (r or {}).get("monitorName", "")
                if mon_name:
                    extra = f"，{mon_name}" if mon_name else ""
                    if injected:
                        return f"已为{game_name}开启HDR，亮度{hdr.get('brightness')}、对比度{hdr.get('contrast')}、色温{hdr.get('color_temp')}{extra}，ReShade shader 已注入"
                    return f"已为{game_name}开启HDR，亮度{hdr.get('brightness')}、对比度{hdr.get('contrast')}、色温{hdr.get('color_temp')}{extra}"
            if injected:
                return f"已为{game_name}开启HDR，亮度{hdr.get('brightness')}、对比度{hdr.get('contrast')}、色温{hdr.get('color_temp')}，ReShade shader 已注入"
            return f"已为{game_name}开启HDR，亮度{hdr.get('brightness')}、对比度{hdr.get('contrast')}、色温{hdr.get('color_temp')}"

        # 构造 TTS 回复
        ctrl_name = {"brightness": "亮度", "contrast": "对比度", "volume": "音量", "color_temp": "色温"}.get(control, control)
        # 多显示器时才在回复中说明是哪个显示器
        if mon_name and self._count_monitors() > 1:
            reply = f"好的，已将{mon_name}的{ctrl_name}设为{value}%"
        else:
            reply = f"好的，已将{ctrl_name}设为{value}%"
        return reply

    # ── RenoDX 游戏支持 ──────────────────────────────────────────────────────
    _RENODX_GAMES = {
        "eldenring.exe": "艾尔登法环",
        "eboot.bin": "只狼",
        "sekiro.exe": "只狼",
        "blackmythwukong.exe": "黑神话悟空",
        "wukong.exe": "黑神话悟空",
        "cyberpunk2077.exe": "赛博朋克2077",
        "cp2077.exe": "赛博朋克2077",
        "hogwartslegacy.exe": "霍格沃茨之遗",
        "hogwarts legacy.exe": "霍格沃茨之遗",
        "baldursgate3.exe": "博德之门3",
        "bg3.exe": "博德之门3",
        "devilmaycry5.exe": "鬼泣5",
        "dmc5.exe": "鬼泣5",
        "dmc5demo.exe": "鬼泣5",
        "devilmaycry5hd.exe": "鬼泣5",
        "monsterhunterrise.exe": "怪物猎人崛起",
        "mhrise.exe": "怪物猎人崛起",
        "mhrise_s.exe": "怪物猎人崛起",
        "monsterhunterworld.exe": "怪物猎人世界",
        "mhworld.exe": "怪物猎人世界",
        "mhw.exe": "怪物猎人世界",
        "resident evil 2.exe": "生化危机2重制版",
        "re2.exe": "生化危机2重制版",
        "resident evil 3.exe": "生化危机3重制版",
        "re3.exe": "生化危机3重制版",
        "resident evil 4 remake.exe": "生化危机4重制版",
        "re4.exe": "生化危机4重制版",
        "resident evil 7.exe": "生化危机7",
        "re7.exe": "生化危机7",
        "resident evil village.exe": "生化危机村庄",
        "re8.exe": "生化危机村庄",
        "ghostwiretokyo.exe": "幽灵线东京",
        "gwt.exe": "幽灵线东京",
        "deadisland2.exe": "死亡岛2",
        "deathstranding.exe": "死亡搁浅",
        "deathstranding_pc_steam.exe": "死亡搁浅",
        "metro exodus.exe": "地铁离去",
        "metro.exe": "地铁离去",
        "metroexodus.exe": "地铁离去",
        "control.exe": "控制",
        "alanwake2.exe": "Alan Wake 2",
        "alan_wake_2.exe": "Alan Wake 2",
        "gta5.exe": "GTA5",
        "gtaonline.exe": "GTA5",
        "nier replicant ver1.22474487139.exe": "Nier Replicant",
        "nierautomata.exe": "尼尔机械纪元",
        "nier.exe": "尼尔机械纪元",
        "rdr2.exe": "大镖客2",
        "reddeadredemption2.exe": "大镖客2",
        "lieofp.exe": "Lies of P",
        "liesofp.exe": "Lies of P",
        "shadow of the tomb raider.exe": "古墓丽影暗影",
        "shadowofthetombraider.exe": "古墓丽影暗影",
        "sottr.exe": "古墓丽影暗影",
        "rise of the tomb raider.exe": "古墓丽影崛起",
        "metro2033redux.exe": "地铁2033",
        "metro-lastlightredux.exe": "地铁流亡",
        "darksiders3.exe": "暗黑血统3",
        "darksiders_warmastered.exe": "暗黑血统原罪初版",
        "uncharted4.exe": "神秘海域4",
        "uncharted llc.exe": "神秘海域失落遗产",
        "spiderman.exe": "蜘蛛侠重制版",
        "spidermanremastered.exe": "蜘蛛侠重制版",
        "spiderman-milesmorales.exe": "蜘蛛侠迈尔斯",
        "spidermanmilesmorales.exe": "蜘蛛侠迈尔斯",
        "miles morales.exe": "蜘蛛侠迈尔斯",
        "spiderman-2.exe": "蜘蛛侠2",
        "spiderman2.exe": "蜘蛛侠2",
        "god of war.exe": "战神",
        "gow.exe": "战神",
        "god of war ragnarok.exe": "战神诸神黄昏",
        "gowr.exe": "战神诸神黄昏",
        "forza horizon 5.exe": "极限竞速地平线5",
        "forzahorizon5.exe": "极限竞速地平线5",
        "f12024.exe": "F1 24",
        "f12023.exe": "F1 23",
        "f122.exe": "F1 22",
        "assassins creed valhalla.exe": "刺客信条英灵殿",
        "valhalla.exe": "刺客信条英灵殿",
        "assassins creed odyssey.exe": "刺客信条奥德赛",
        "odyssey.exe": "刺客信条奥德赛",
        "assassins creed origins.exe": "刺客信条起源",
        "assassins creed mirage.exe": "刺客信条幻景",
        "acmirage.exe": "刺客信条幻景",
        "assassins creed syndicate.exe": "刺客信条辛迪加",
        "assassins creed unity.exe": "刺客信条大革命",
        "acunity.exe": "刺客信条大革命",
        "assassins creed black flag.exe": "刺客信条黑旗",
        "assassins creed revelations.exe": "刺客信条启示录",
        "assassins creed 3 remastered.exe": "刺客信条3重制版",
        "assassins creed rogue.exe": "刺客信条枭雄",
        "wutheringwaves.exe": "鸣潮",
        "wwgame.pc.launcher.exe": "鸣潮",
        "wwgame.exe": "鸣潮",
        "genshinimpact.exe": "原神",
        "yuanyang.exe": "原神",
        "hsrgame.exe": "崩坏星穹铁道",
        "hkrpg.exe": "崩坏3",
        "bh3.exe": "崩坏3",
        "honkaistarrail.exe": "崩坏星穹铁道",
        "star rail.exe": "崩坏星穹铁道",
        "zenlesszonezero.exe": "绝区零",
        "zzz.exe": "绝区零",
        "zzz_launcher.exe": "绝区零",
        "apexlegends.exe": "Apex英雄",
        "r5apex.exe": "Apex英雄",
        "valorant.exe": "无畏契约",
        "valorant-win-shipping.exe": "无畏契约",
        "csgo.exe": "CS2",
        "cs2.exe": "CS2",
        "lostark.exe": "失落的方舟",
        "lostarkshared.exe": "失落的方舟",
        "lostarklauncher.exe": "失落的方舟",
        "diablo4.exe": "暗黑破坏神4",
        "d4.exe": "暗黑破坏神4",
        "overwatch 2.exe": "守望先锋2",
        "overwatch2.exe": "守望先锋2",
        "ow2.exe": "守望先锋2",
        "wow.exe": "魔兽世界",
        "wowclassic.exe": "魔兽世界经典",
        "wowclassic_era.exe": "魔兽世界经典怀旧",
        "wowt.exe": "魔兽世界",
        "league of legends.exe": "英雄联盟",
        "leagueclient.exe": "英雄联盟",
        "riotgames-league-of-legends.exe": "英雄联盟",
        "client.exe": "客户端",
        "steam.exe": "Steam",
        "epicgameslauncher.exe": "Epic",
        "origingameclient.exe": "Origin",
        "ubisoft game launcher.exe": "Ubisoft",
        "minecraft-launcher.exe": "我的世界",
        "javaw.exe": "Java程序",
        "code.exe": "VS Code",
        "devenv.exe": "Visual Studio",
        "pycharm64.exe": "PyCharm",
        "idea64.exe": "IntelliJ IDEA",
        "notepad++.exe": "Notepad++",
        "tasklist.exe": "(系统)",
        "explorer.exe": "(资源管理器)",
        "dwm.exe": "(系统)",
        "searchui.exe": "(系统)",
        "searchhost.exe": "(系统)",
        "runtimebroker.exe": "(系统)",
        "shellexperiencehost.exe": "(系统)",
        "startmenuexperiencehost.exe": "(系统)",
        "widgetservice.exe": "(系统)",
        "applicationframehost.exe": "(应用)",
        "windowsterminal.exe": "(终端)",
        "conhost.exe": "(系统)",
        "sihost.exe": "(系统)",
        "fontdrvhost.exe": "(系统)",
        "winlogon.exe": "(系统)",
        "services.exe": "(系统)",
        "lsass.exe": "(系统)",
        "svchost.exe": "(系统)",
        "systemsettings.exe": "(设置)",
    }

    # RenoDX addon 下载/安装信息（exe -> addon信息）
    _RENODX_ADDONS = {
        "1000xresist.exe": {
            "url": "https://mohannedelfatih.github.io/renodx/renodx-1000xresist.addon64",
            "addon_name": "renodx-1000xresist.addon64",
            "path": None,
            "hdr_values": {"brightness": 75, "contrast": 72, "color_temp": 55},
        },
        "absolum.exe": {
            "url": "https://oopydoopy.github.io/renodx/renodx-absolum.addon64",
            "addon_name": "renodx-absolum.addon64",
            "path": None,
            "hdr_values": {"brightness": 75, "contrast": 72, "color_temp": 55},
        },
        "ac_odyssey_sp.exe": {
            "url": "https://github.com/mqhaji/renodx/releases/download/snapshot/renodx-asscreedorigins-odyssey.addon64",
            "addon_name": "renodx-asscreedorigins-odyssey.addon64",
            "path": None,
            "hdr_values": {"brightness": 75, "contrast": 72, "color_temp": 55},
        },
        "ac_valhalla_sp.exe": {
            "url": "https://github.com/mqhaji/renodx/releases/download/snapshot/renodx-asscreedorigins-odyssey.addon64",
            "addon_name": "renodx-asscreedorigins-odyssey.addon64",
            "path": None,
            "hdr_values": {"brightness": 75, "contrast": 72, "color_temp": 55},
        },
        "ace7.exe": {
            "url": "https://clshortfuse.github.io/renodx/renodx-acecombat7.addon64",
            "addon_name": "renodx-acecombat7.addon64",
            "path": None,
            "hdr_values": {"brightness": 75, "contrast": 72, "color_temp": 55},
        },
        "ace7_skiesunknown.exe": {
            "url": "https://clshortfuse.github.io/renodx/renodx-acecombat7.addon64",
            "addon_name": "renodx-acecombat7.addon64",
            "path": None,
            "hdr_values": {"brightness": 75, "contrast": 72, "color_temp": 55},
        },
        "acorigins_sp.exe": {
            "url": "https://github.com/mqhaji/renodx/releases/download/snapshot/renodx-asscreedorigins-odyssey.addon64",
            "addon_name": "renodx-asscreedorigins-odyssey.addon64",
            "path": None,
            "hdr_values": {"brightness": 75, "contrast": 72, "color_temp": 55},
        },
        "acvalhalla.exe": {
            "url": "https://github.com/mqhaji/renodx/releases/download/snapshot/renodx-asscreedorigins-odyssey.addon64",
            "addon_name": "renodx-asscreedorigins-odyssey.addon64",
            "path": None,
            "hdr_values": {"brightness": 75, "contrast": 72, "color_temp": 55},
        },
        "againstthestorm.exe": {
            "url": "https://github.com/pmnoxx/renodx/releases/download/snapshot/renodx-_univ.addon64",
            "addon_name": "renodx-_univ.addon64",
            "path": None,
            "hdr_values": {"brightness": 75, "contrast": 72, "color_temp": 55},
        },
        "animalwell.exe": {
            "url": "https://clshortfuse.github.io/renodx/renodx-animalwell.addon64",
            "addon_name": "renodx-animalwell.addon64",
            "path": None,
            "hdr_values": {"brightness": 75, "contrast": 72, "color_temp": 55},
        },
        "armoredcore6.exe": {
            "url": "https://clshortfuse.github.io/renodx/renodx-fromsoft_engine.addon64",
            "addon_name": "renodx-fromsoft_engine.addon64",
            "path": None,
            "hdr_values": {"brightness": 75, "contrast": 72, "color_temp": 55},
        },
        "berserkbotb.exe": {
            "url": "https://marat569.github.io/renodx/renodx-BerserkBotH.addon64",
            "addon_name": "renodx-BerserkBotH.addon64",
            "path": None,
            "hdr_values": {"brightness": 75, "contrast": 72, "color_temp": 55},
        },
        "blackmythwukong.exe": {
            "url": "https://github.com/PudingJelly/BlackMythWukong-HDR/releases/download/published/renodx-blackmythwukong.addon64",
            "addon_name": "renodx-blackmythwukong.addon64",
            "path": None,
            "hdr_values": {"brightness": 75, "contrast": 70, "color_temp": 50},
        },
        "citizensleeper2.exe": {
            "url": "https://clshortfuse.github.io/renodx/renodx-citizensleeper2.addon64",
            "addon_name": "renodx-citizensleeper2.addon64",
            "path": None,
            "hdr_values": {"brightness": 75, "contrast": 72, "color_temp": 55},
        },
        "cp2077.exe": {
            "url": "https://clshortfuse.github.io/renodx/renodx-cp2077.addon64",
            "addon_name": "renodx-cp2077.addon64",
            "path": None,
            "hdr_values": {"brightness": 60, "contrast": 65, "color_temp": 50},
        },
        "cyberpunk2077.exe": {
            "url": "https://clshortfuse.github.io/renodx/renodx-cp2077.addon64",
            "addon_name": "renodx-cp2077.addon64",
            "path": None,
            "hdr_values": {"brightness": 60, "contrast": 65, "color_temp": 50},
        },
        "darkestdungeon2.exe": {
            "url": "https://github.com/pmnoxx/renodx/releases/download/snapshot/renodx-_univ.addon64",
            "addon_name": "renodx-_univ.addon64",
            "path": None,
            "hdr_values": {"brightness": 75, "contrast": 72, "color_temp": 55},
        },
        "deadislandde.exe": {
            "url": "https://notvoosh.github.io/renodx/renodx-deadislandde.addon64",
            "addon_name": "renodx-deadislandde.addon64",
            "path": None,
            "hdr_values": {"brightness": 75, "contrast": 72, "color_temp": 55},
        },
        "doometernal.exe": {
            "url": "https://github.com/clshortfuse/renodx/releases/download/snapshot/renodx-doom-eternal.addon64",
            "addon_name": "renodx-doom-eternal.addon64",
            "path": None,
            "hdr_values": {"brightness": 75, "contrast": 72, "color_temp": 55},
        },
        "eboot.bin": {
            "url": "https://clshortfuse.github.io/renodx/renodx-fromsoft_engine.addon64",
            "addon_name": "renodx-fromsoft_engine.addon64",
            "path": None,
            "hdr_values": {"brightness": 80, "contrast": 75, "color_temp": 55},
        },
        "eldenring.exe": {
            "url": "https://clshortfuse.github.io/renodx/renodx-fromsoft_engine.addon64",
            "addon_name": "renodx-fromsoft_engine.addon64",
            "path": None,
            "hdr_values": {"brightness": 80, "contrast": 75, "color_temp": 55},
        },
        "endermagnolia.exe": {
            "url": "https://marat569.github.io/renodx/renodx-endermagnolia.addon64",
            "addon_name": "renodx-endermagnolia.addon64",
            "path": None,
            "hdr_values": {"brightness": 75, "contrast": 72, "color_temp": 55},
        },
        "f12023.exe": {
            "url": "https://oopydoopy.github.io/renodx/renodx-forzahorizon6.addon64",
            "addon_name": "renodx-forzahorizon6.addon64",
            "path": None,
            "hdr_values": {"brightness": 75, "contrast": 72, "color_temp": 55},
        },
        "f12024.exe": {
            "url": "https://oopydoopy.github.io/renodx/renodx-forzahorizon6.addon64",
            "addon_name": "renodx-forzahorizon6.addon64",
            "path": None,
            "hdr_values": {"brightness": 75, "contrast": 72, "color_temp": 55},
        },
        "f122.exe": {
            "url": "https://oopydoopy.github.io/renodx/renodx-forzahorizon6.addon64",
            "addon_name": "renodx-forzahorizon6.addon64",
            "path": None,
            "hdr_values": {"brightness": 75, "contrast": 72, "color_temp": 55},
        },
        "fantasianneodimension.exe": {
            "url": "https://marat569.github.io/renodx/renodx-fantasianneodimension.addon64",
            "addon_name": "renodx-fantasianneodimension.addon64",
            "path": None,
            "hdr_values": {"brightness": 75, "contrast": 72, "color_temp": 55},
        },
        "farcry5.exe": {
            "url": "https://clshortfuse.github.io/renodx/renodx-farcry5.addon64",
            "addon_name": "renodx-farcry5.addon64",
            "path": None,
            "hdr_values": {"brightness": 75, "contrast": 72, "color_temp": 55},
        },
        "farcry6.exe": {
            "url": "https://github.com/mqhaji/renodx/releases/download/snapshot/renodx-farcry6.addon64",
            "addon_name": "renodx-farcry6.addon64",
            "path": None,
            "hdr_values": {"brightness": 75, "contrast": 72, "color_temp": 55},
        },
        "ff14.exe": {
            "url": "https://clshortfuse.github.io/renodx/renodx-ffxiv.addon64",
            "addon_name": "renodx-ffxiv.addon64",
            "path": None,
            "hdr_values": {"brightness": 75, "contrast": 72, "color_temp": 55},
        },
        "ffxiv.exe": {
            "url": "https://clshortfuse.github.io/renodx/renodx-ffxiv.addon64",
            "addon_name": "renodx-ffxiv.addon64",
            "path": None,
            "hdr_values": {"brightness": 75, "contrast": 72, "color_temp": 55},
        },
        "forzahorizon6.exe": {
            "url": "https://oopydoopy.github.io/renodx/renodx-forzahorizon6.addon64",
            "addon_name": "renodx-forzahorizon6.addon64",
            "path": None,
            "hdr_values": {"brightness": 75, "contrast": 72, "color_temp": 55},
        },
        "ghostwiretokyo.exe": {
            "url": "https://github.com/mqhaji/renodx/releases/download/snapshot/renodx-ghostwiretokyo.addon64",
            "addon_name": "renodx-ghostwiretokyo.addon64",
            "path": None,
            "hdr_values": {"brightness": 75, "contrast": 72, "color_temp": 55},
        },
        "gta5.exe": {
            "url": "https://clshortfuse.github.io/renodx/renodx-gtav-enhanced.addon64",
            "addon_name": "renodx-gtav-enhanced.addon64",
            "path": None,
            "hdr_values": {"brightness": 75, "contrast": 72, "color_temp": 55},
        },
        "gtaonline.exe": {
            "url": "https://clshortfuse.github.io/renodx/renodx-gtav-enhanced.addon64",
            "addon_name": "renodx-gtav-enhanced.addon64",
            "path": None,
            "hdr_values": {"brightness": 75, "contrast": 72, "color_temp": 55},
        },
        "hadesii.exe": {
            "url": "https://clshortfuse.github.io/renodx/renodx-hades2.addon64",
            "addon_name": "renodx-hades2.addon64",
            "path": None,
            "hdr_values": {"brightness": 75, "contrast": 72, "color_temp": 55},
        },
        "hardresetredux.exe": {
            "url": "https://clshortfuse.github.io/renodx/renodx-roadhogengine.addon64",
            "addon_name": "renodx-roadhogengine.addon64",
            "path": None,
            "hdr_values": {"brightness": 75, "contrast": 72, "color_temp": 55},
        },
        "hardspaceshipbreaker.exe": {
            "url": "https://github.com/pmnoxx/renodx/releases/download/snapshot/renodx-_univ.addon64",
            "addon_name": "renodx-_univ.addon64",
            "path": None,
            "hdr_values": {"brightness": 75, "contrast": 72, "color_temp": 55},
        },
        "honkaistarrail.exe": {
            "url": "https://clshortfuse.github.io/renodx/renodx-honkai-starrail.addon64",
            "addon_name": "renodx-honkai-starrail.addon64",
            "path": None,
            "hdr_values": {"brightness": 75, "contrast": 72, "color_temp": 55},
        },
        "ixion.exe": {
            "url": "https://github.com/pmnoxx/renodx/releases/download/snapshot/renodx-_univ.addon64",
            "addon_name": "renodx-_univ.addon64",
            "path": None,
            "hdr_values": {"brightness": 75, "contrast": 72, "color_temp": 55},
        },
        "kingdomcome2.exe": {
            "url": "https://clshortfuse.github.io/renodx/renodx-kingdomcome2.addon64",
            "addon_name": "renodx-kingdomcome2.addon64",
            "path": None,
            "hdr_values": {"brightness": 75, "contrast": 72, "color_temp": 55},
        },
        "lunacid.exe": {
            "url": "https://oopydoopy.github.io/renodx/renodx-lunacid.addon64",
            "addon_name": "renodx-lunacid.addon64",
            "path": None,
            "hdr_values": {"brightness": 75, "contrast": 72, "color_temp": 55},
        },
        "mafia2.exe": {
            "url": "https://clshortfuse.github.io/renodx/renodx-mafiade.addon64",
            "addon_name": "renodx-mafiade.addon64",
            "path": None,
            "hdr_values": {"brightness": 75, "contrast": 72, "color_temp": 55},
        },
        "mariokart8.exe": {
            "url": "https://souperman9.github.io/renodx/renodx-mk8.addon64",
            "addon_name": "renodx-mk8.addon64",
            "path": None,
            "hdr_values": {"brightness": 75, "contrast": 72, "color_temp": 55},
        },
        "metaphorrefantazio.exe": {
            "url": "https://mohannedelfatih.github.io/renodx/renodx-metaphorrefantazio.addon64",
            "addon_name": "renodx-metaphorrefantazio.addon64",
            "path": None,
            "hdr_values": {"brightness": 75, "contrast": 72, "color_temp": 55},
        },
        "nier replicant ver1.22474487139.exe": {
            "url": "https://akuru-q.github.io/renodx/renodx-nierreplicant.addon64",
            "addon_name": "renodx-nierreplicant.addon64",
            "path": None,
            "hdr_values": {"brightness": 75, "contrast": 72, "color_temp": 55},
        },
        "nier.exe": {
            "url": "https://clshortfuse.github.io/renodx/renodx-nierautomata.addon64",
            "addon_name": "renodx-nierautomata.addon64",
            "path": None,
            "hdr_values": {"brightness": 75, "contrast": 72, "color_temp": 55},
        },
        "nierautomata.exe": {
            "url": "https://clshortfuse.github.io/renodx/renodx-nierautomata.addon64",
            "addon_name": "renodx-nierautomata.addon64",
            "path": None,
            "hdr_values": {"brightness": 75, "contrast": 72, "color_temp": 55},
        },
        "nights of azure 1.exe": {
            "url": "https://marat569.github.io/renodx/renodx-nightsofazure1.addon64",
            "addon_name": "renodx-nightsofazure1.addon64",
            "path": None,
            "hdr_values": {"brightness": 75, "contrast": 72, "color_temp": 55},
        },
        "nights of azure 2.exe": {
            "url": "https://marat569.github.io/renodx/renodx-nightsofazure2.addon64",
            "addon_name": "renodx-nightsofazure2.addon64",
            "path": None,
            "hdr_values": {"brightness": 75, "contrast": 72, "color_temp": 55},
        },
        "outerwilds.exe": {
            "url": "https://mohannedelfatih.github.io/renodx/renodx-outerwilds.addon64",
            "addon_name": "renodx-outerwilds.addon64",
            "path": None,
            "hdr_values": {"brightness": 75, "contrast": 72, "color_temp": 55},
        },
        "pathofexile2.exe": {
            "url": "https://sgtforgery.github.io/renodx/renodx-poe2.addon64",
            "addon_name": "renodx-poe2.addon64",
            "path": None,
            "hdr_values": {"brightness": 75, "contrast": 72, "color_temp": 55},
        },
        "poe2.exe": {
            "url": "https://sgtforgery.github.io/renodx/renodx-poe2.addon64",
            "addon_name": "renodx-poe2.addon64",
            "path": None,
            "hdr_values": {"brightness": 75, "contrast": 72, "color_temp": 55},
        },
        "re2.exe": {
            "url": "https://github.com/mqhaji/renodx/releases/download/snapshot/renodx-re7-2r-3r-village.addon64",
            "addon_name": "renodx-re7-2r-3r-village.addon64",
            "path": None,
            "hdr_values": {"brightness": 75, "contrast": 72, "color_temp": 55},
        },
        "re3.exe": {
            "url": "https://github.com/mqhaji/renodx/releases/download/snapshot/renodx-re7-2r-3r-village.addon64",
            "addon_name": "renodx-re7-2r-3r-village.addon64",
            "path": None,
            "hdr_values": {"brightness": 75, "contrast": 72, "color_temp": 55},
        },
        "re4.exe": {
            "url": "https://github.com/mqhaji/renodx/releases/download/snapshot/renodx-re4remake.addon64",
            "addon_name": "renodx-re4remake.addon64",
            "path": None,
            "hdr_values": {"brightness": 75, "contrast": 72, "color_temp": 55},
        },
        "re4_re.exe": {
            "url": "https://github.com/mqhaji/renodx/releases/download/snapshot/renodx-re4remake.addon64",
            "addon_name": "renodx-re4remake.addon64",
            "path": None,
            "hdr_values": {"brightness": 75, "contrast": 72, "color_temp": 55},
        },
        "re4re.exe": {
            "url": "https://github.com/mqhaji/renodx/releases/download/snapshot/renodx-re4remake.addon64",
            "addon_name": "renodx-re4remake.addon64",
            "path": None,
            "hdr_values": {"brightness": 75, "contrast": 72, "color_temp": 55},
        },
        "re7.exe": {
            "url": "https://github.com/mqhaji/renodx/releases/download/snapshot/renodx-re7-2r-3r-village.addon64",
            "addon_name": "renodx-re7-2r-3r-village.addon64",
            "path": None,
            "hdr_values": {"brightness": 75, "contrast": 72, "color_temp": 55},
        },
        "re8.exe": {
            "url": "https://github.com/mqhaji/renodx/releases/download/snapshot/renodx-re7-2r-3r-village.addon64",
            "addon_name": "renodx-re7-2r-3r-village.addon64",
            "path": None,
            "hdr_values": {"brightness": 75, "contrast": 72, "color_temp": 55},
        },
        "riseoftheronin.exe": {
            "url": "https://marat569.github.io/renodx/renodx-riseofronin.addon64",
            "addon_name": "renodx-riseofronin.addon64",
            "path": None,
            "hdr_values": {"brightness": 75, "contrast": 72, "color_temp": 55},
        },
        "robocoproguecity.exe": {
            "url": "https://github.com/mqhaji/renodx/releases/download/snapshot/renodx-routine.addon64",
            "addon_name": "renodx-routine.addon64",
            "path": None,
            "hdr_values": {"brightness": 75, "contrast": 72, "color_temp": 55},
        },
        "routineroguecity.exe": {
            "url": "https://mqhaji.github.io/renodx/renodx-robocop.addon64",
            "addon_name": "renodx-robocop.addon64",
            "path": None,
            "hdr_values": {"brightness": 75, "contrast": 72, "color_temp": 55},
        },
        "saoalicization.exe": {
            "url": "https://github.com/Toru77/renodx/releases/download/snapshot/renodx-sao-alicization.addon64",
            "addon_name": "renodx-sao-alicization.addon64",
            "path": None,
            "hdr_values": {"brightness": 75, "contrast": 72, "color_temp": 55},
        },
        "sekiro.exe": {
            "url": "https://clshortfuse.github.io/renodx/renodx-fromsoft_engine.addon64",
            "addon_name": "renodx-fromsoft_engine.addon64",
            "path": None,
            "hdr_values": {"brightness": 80, "contrast": 75, "color_temp": 55},
        },
        "silent hill 2 remake.exe": {
            "url": "https://clshortfuse.github.io/renodx/renodx-silenthill2remake.addon64",
            "addon_name": "renodx-silenthill2remake.addon64",
            "path": None,
            "hdr_values": {"brightness": 75, "contrast": 72, "color_temp": 55},
        },
        "silent hill 2.exe": {
            "url": "https://clshortfuse.github.io/renodx/renodx-silenthill2remake.addon64",
            "addon_name": "renodx-silenthill2remake.addon64",
            "path": None,
            "hdr_values": {"brightness": 75, "contrast": 72, "color_temp": 55},
        },
        "sonic unleashed.exe": {
            "url": "https://akuru-q.github.io/renodx/renodx-sonicunleashedrecomp.addon64",
            "addon_name": "renodx-sonicunleashedrecomp.addon64",
            "path": None,
            "hdr_values": {"brightness": 75, "contrast": 72, "color_temp": 55},
        },
        "sopffo.exe": {
            "url": "https://akuru-q.github.io/renodx/renodx-sopffo.addon64",
            "addon_name": "renodx-sopffo.addon64",
            "path": None,
            "hdr_values": {"brightness": 75, "contrast": 72, "color_temp": 55},
        },
        "spiderman-milesmorales.exe": {
            "url": "https://github.com/mqhaji/renodx/releases/download/snapshot/renodx-spiderman_2018_miles.addon64",
            "addon_name": "renodx-spiderman_2018_miles.addon64",
            "path": None,
            "hdr_values": {"brightness": 75, "contrast": 72, "color_temp": 55},
        },
        "spiderman2.exe": {
            "url": "https://github.com/mqhaji/renodx/releases/download/snapshot/renodx-spiderman_2018_miles.addon64",
            "addon_name": "renodx-spiderman_2018_miles.addon64",
            "path": None,
            "hdr_values": {"brightness": 75, "contrast": 72, "color_temp": 55},
        },
        "spidermanremastered.exe": {
            "url": "https://github.com/mqhaji/renodx/releases/download/snapshot/renodx-spiderman_2018_miles.addon64",
            "addon_name": "renodx-spiderman_2018_miles.addon64",
            "path": None,
            "hdr_values": {"brightness": 75, "contrast": 72, "color_temp": 55},
        },
        "strangerofparadise.exe": {
            "url": "https://akuru-q.github.io/renodx/renodx-sopffo.addon64",
            "addon_name": "renodx-sopffo.addon64",
            "path": None,
            "hdr_values": {"brightness": 75, "contrast": 72, "color_temp": 55},
        },
        "sw2.exe": {
            "url": "https://clshortfuse.github.io/renodx/renodx-roadhogengine.addon64",
            "addon_name": "renodx-roadhogengine.addon64",
            "path": None,
            "hdr_values": {"brightness": 75, "contrast": 72, "color_temp": 55},
        },
        "sw2013.exe": {
            "url": "https://clshortfuse.github.io/renodx/renodx-roadhogengine.addon64",
            "addon_name": "renodx-roadhogengine.addon64",
            "path": None,
            "hdr_values": {"brightness": 75, "contrast": 72, "color_temp": 55},
        },
        "teardown.exe": {
            "url": "https://notvoosh.github.io/renodx/renodx-teardown.addon64",
            "addon_name": "renodx-teardown.addon64",
            "path": None,
            "hdr_values": {"brightness": 75, "contrast": 72, "color_temp": 55},
        },
        "the evil within 2.exe": {
            "url": "https://marat569.github.io/renodx/renodx-tew2.addon64",
            "addon_name": "renodx-tew2.addon64",
            "path": None,
            "hdr_values": {"brightness": 75, "contrast": 72, "color_temp": 55},
        },
        "the hundred line.exe": {
            "url": "https://clshortfuse.github.io/renodx/renodx-thehundredline.addon64",
            "addon_name": "renodx-thehundredline.addon64",
            "path": None,
            "hdr_values": {"brightness": 75, "contrast": 72, "color_temp": 55},
        },
        "the legend of zelda botw.exe": {
            "url": "https://souperman9.github.io/renodx/renodx-botw.addon64",
            "addon_name": "renodx-botw.addon64",
            "path": None,
            "hdr_values": {"brightness": 75, "contrast": 72, "color_temp": 55},
        },
        "the legend of zelda totk.exe": {
            "url": "https://souperman9.github.io/renodx/renodx-totk.addon64",
            "addon_name": "renodx-totk.addon64",
            "path": None,
            "hdr_values": {"brightness": 75, "contrast": 72, "color_temp": 55},
        },
        "thelegendofzelda.exe": {
            "url": "https://souperman9.github.io/renodx/renodx-botw.addon64",
            "addon_name": "renodx-botw.addon64",
            "path": None,
            "hdr_values": {"brightness": 75, "contrast": 72, "color_temp": 55},
        },
        "thevanhelsing.exe": {
            "url": "https://notvoosh.github.io/renodx/renodx-vanhelsingfinalcut.addon64",
            "addon_name": "renodx-vanhelsingfinalcut.addon64",
            "path": None,
            "hdr_values": {"brightness": 75, "contrast": 72, "color_temp": 55},
        },
        "trine2.exe": {
            "url": "https://github.com/chrisboyer2/renodx/releases/download/v2.0/renodx-trine2.addon64",
            "addon_name": "renodx-trine2.addon64",
            "path": None,
            "hdr_values": {"brightness": 75, "contrast": 72, "color_temp": 55},
        },
        "village_re.exe": {
            "url": "https://github.com/mqhaji/renodx/releases/download/snapshot/renodx-re7-2r-3r-village.addon64",
            "addon_name": "renodx-re7-2r-3r-village.addon64",
            "path": None,
            "hdr_values": {"brightness": 75, "contrast": 72, "color_temp": 55},
        },
        "witcher3de.exe": {
            "url": "https://oopydoopy.github.io/renodx/renodx-thewitcher3.addon64",
            "addon_name": "renodx-thewitcher3.addon64",
            "path": None,
            "hdr_values": {"brightness": 75, "contrast": 72, "color_temp": 55},
        },
        "wolongfallendynasty.exe": {
            "url": "https://akuru-q.github.io/renodx/renodx-wolong.addon64",
            "addon_name": "renodx-wolong.addon64",
            "path": None,
            "hdr_values": {"brightness": 75, "contrast": 72, "color_temp": 55},
        },
        "wuchangfallenfeathers.exe": {
            "url": "https://oopydoopy.github.io/renodx/renodx-wuchang.addon64",
            "addon_name": "renodx-wuchang.addon64",
            "path": None,
            "hdr_values": {"brightness": 75, "contrast": 72, "color_temp": 55},
        },
        "wukong.exe": {
            "url": "https://github.com/PudingJelly/BlackMythWukong-HDR/releases/download/published/renodx-blackmythwukong.addon64",
            "addon_name": "renodx-blackmythwukong.addon64",
            "path": None,
            "hdr_values": {"brightness": 75, "contrast": 70, "color_temp": 50},
        },
        "xcxde.exe": {
            "url": "https://souperman9.github.io/renodx/renodx-xbcx.addon64",
            "addon_name": "renodx-xbcx.addon64",
            "path": None,
            "hdr_values": {"brightness": 75, "contrast": 72, "color_temp": 55},
        },
        "xenobladechroniclesxde.exe": {
            "url": "https://souperman9.github.io/renodx/renodx-xbcx.addon64",
            "addon_name": "renodx-xbcx.addon64",
            "path": None,
            "hdr_values": {"brightness": 75, "contrast": 72, "color_temp": 55},
        },
        "yakuza0.exe": {
            "url": "https://akuru-q.github.io/renodx/renodx-yakuza0.addon64",
            "addon_name": "renodx-yakuza0.addon64",
            "path": None,
            "hdr_values": {"brightness": 75, "contrast": 72, "color_temp": 55},
        },
        "ysixmonstrumnox.exe": {
            "url": "https://danaforever.github.io/renodx/renodx-ys9.addon64",
            "addon_name": "renodx-ys9.addon64",
            "path": None,
            "hdr_values": {"brightness": 75, "contrast": 72, "color_temp": 55},
        },
        "ysx nordics.exe": {
            "url": "https://marat569.github.io/renodx/renodx-ys10.addon64",
            "addon_name": "renodx-ys10.addon64",
            "path": None,
            "hdr_values": {"brightness": 75, "contrast": 72, "color_temp": 55},
        },
        "ysxproudnordics.exe": {
            "url": "https://github.com/Toru77/renodx/releases/download/snapshot/renodx-ys10pn.addon64",
            "addon_name": "renodx-ys10pn.addon64",
            "path": None,
            "hdr_values": {"brightness": 75, "contrast": 72, "color_temp": 55},
        },
        "zelda_botw.exe": {
            "url": "https://souperman9.github.io/renodx/renodx-botw.addon64",
            "addon_name": "renodx-botw.addon64",
            "path": None,
            "hdr_values": {"brightness": 75, "contrast": 72, "color_temp": 55},
        },
        "zelda_totk.exe": {
            "url": "https://souperman9.github.io/renodx/renodx-totk.addon64",
            "addon_name": "renodx-totk.addon64",
            "path": None,
            "hdr_values": {"brightness": 75, "contrast": 72, "color_temp": 55},
        },

        "ffxv.exe": {
            "url": "https://danaforever.github.io/renodx/renodx-ffxv.addon64",
            "addon_name": "renodx-ffxv.addon64",
            "path": None,
            "hdr_values": {'brightness': 75, 'contrast': 72, 'color_temp': 55},
        },
        "mhrise.exe": {
            "url": "https://github.com/Izueh/renodx/releases/download/snapshot/renodx-mhrise.addon64",
            "addon_name": "renodx-mhrise.addon64",
            "path": None,
            "hdr_values": {'brightness': 75, 'contrast': 72, 'color_temp': 55},
        },
        "nierautomata.exe": {
            "url": "https://clshortfuse.github.io/renodx/renodx-nierautomata.addon64",
            "addon_name": "renodx-nierautomata.addon64",
            "path": None,
            "hdr_values": {'brightness': 75, 'contrast': 72, 'color_temp': 55},
        },
        "starfield.exe": {
            "url": "https://clshortfuse.github.io/renodx/renodx-starfield.addon64",
            "addon_name": "renodx-starfield.addon64",
            "path": None,
            "hdr_values": {'brightness': 75, 'contrast': 72, 'color_temp': 55},
        },
        "wutheringwaves.exe": {
            "url": "https://clshortfuse.github.io/renodx/renodx-wutheringwaves.addon64",
            "addon_name": "renodx-wutheringwaves.addon64",
            "path": None,
            "hdr_values": {'brightness': 75, 'contrast': 72, 'color_temp': 55},
        },
        "zenlesszonezero.exe": {
            "url": "https://github.com/MapleHinata/renodx/releases/latest/download/renodx-zenless-zone-zero.addon64",
            "addon_name": "renodx-zenless-zone-zero.addon64",
            "path": None,
            "hdr_values": {'brightness': 75, 'contrast': 72, 'color_temp': 55},
        },
        "zzz.exe": {
            "url": "https://github.com/MapleHinata/renodx/releases/latest/download/renodx-zenless-zone-zero.addon64",
            "addon_name": "renodx-zenless-zone-zero.addon64",
            "path": None,
            "hdr_values": {'brightness': 75, 'contrast': 72, 'color_temp': 55},
        },
    }

    def _get_foreground_process(self):
        """获取前景窗口进程的完整路径"""
        try:
            import ctypes
            from ctypes import windll
            psapi = windll.psapi
            kernel32 = windll.kernel32
            user32 = windll.user32
            GetForegroundWindow = user32.GetForegroundWindow
            GetWindowThreadProcessId = user32.GetWindowThreadProcessId
            OpenProcess = kernel32.OpenProcess
            CloseHandle = kernel32.CloseHandle
            GetModuleFileNameExW = psapi.GetModuleFileNameExW
            PROCESS_QUERY_INFORMATION = 0x0400
            hwnd = GetForegroundWindow()
            if not hwnd:
                return None
            pid = ctypes.c_ulong()
            GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
            h = OpenProcess(PROCESS_QUERY_INFORMATION, False, pid.value)
            if not h:
                return None
            try:
                buf = ctypes.create_unicode_buffer(260)
                if GetModuleFileNameExW(h, 0, buf, 260):
                    return buf.value
            finally:
                CloseHandle(h)
        except Exception as e:
            _flog(f"[游戏检测] 获取进程路径失败: {e}")
        return None

    def _get_foreground_pid(self):
        """获取前景窗口的 PID"""
        try:
            import ctypes
            from ctypes import windll
            user32 = windll.user32
            kernel32 = windll.kernel32
            GetForegroundWindow = user32.GetForegroundWindow
            GetWindowThreadProcessId = user32.GetWindowThreadProcessId
            pid = ctypes.c_ulong()
            GetWindowThreadProcessId(GetForegroundWindow(), ctypes.byref(pid))
            return pid.value if pid.value else None
        except Exception as e:
            _flog(f"[游戏检测] 获取 PID 失败: {e}")
        return None

    def _detect_foreground_game(self):
        """检测前景窗口是否在 RenoDX 支持列表中，返回 (游戏名, addon_info) 或 (None, None)"""
        path = self._get_foreground_process()
        if not path:
            return None, None
        exe = os.path.basename(path).lower()
        name = self._RENODX_GAMES.get(exe)
        addon_info = None
        if exe in self._RENODX_ADDONS:
            addon_info = self._RENODX_ADDONS[exe]
        if name or addon_info:
            _flog(f"[游戏] 检测到: {exe} -> {name or addon_info.get('addon_name')}")
        return name, addon_info

    def _llm_intent_detect(self, text):
        """用 LLM 判断文本是否包含显示器控制意图（含语义理解，支持复合意图）"""
        try:
            prompt = (
                "你是显示器控制意图识别器。判断用户的话是否包含亮度、音量、对比度、色温、HDR控制意图。\n\n"
                "规则：\n"
                "- \"调到/设为/调成\" + 数字 → action=set, value=数字（绝对值）\n"
                "- \"调高/调低/调大/调小\" + 数字 → action=adjust, delta=±数字（相对值）\n"
                "- \"调高/调大/亮一点\"（无数字）→ action=adjust, delta=±10\n"
                "- \"最亮/最暗/最大/最小/静音\" → action=set, value=极值\n\n"
                "语义理解（重要）：\n"
                "- \"刺眼/晃眼/亮瞎/闪瞎/眼睛疼/太高/高了\" → 亮度过高，adjust brightness -10\n"
                "- \"太暗/看不清/黑乎乎/比较低/低了/暗了\" → 亮度过低，adjust brightness +10\n"
                "- \"太吵/炸耳朵/震耳朵/太大声\" → 音量过高，adjust volume -10\n"
                "- \"听不清/听不见/太小声/比较低/小了\" → 音量过低，adjust volume +10\n"
                "- \"闭嘴/安静/别吵了\" → 静音，set volume 0\n"
                "- \"晚上眼睛受不了\" → 亮度过高，adjust brightness -10\n"
                "- \"太冷/偏冷/太蓝\" → 色温过高，adjust color_temp -10\n"
                "- \"太暖/偏暖/太黄\" → 色温过低，adjust color_temp +10\n"
                "- 涉及\"屏幕/显示器/亮度/音量/声音/对比度/色温/HDR/开启HDR\"的抱怨或请求都算控制意图\n\n"
                "复合意图：用户可能同时提到多个控制项，返回JSON数组。\n\n"
                "输出格式：\n"
                "单个意图：{\"action\":\"adjust\",\"control\":\"brightness\",\"delta\":10}\n"
                "多个意图：[{\"action\":\"adjust\",\"control\":\"brightness\",\"delta\":10},{\"action\":\"adjust\",\"control\":\"volume\",\"delta\":10}]\n"
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
                    # 放入 None 到音频队列表示结束
                    self._audio_queue.append(None)
                    break

                if self._interrupted:
                    continue

                # 调用 TTS 生成音频
                audio_data = self._generate_tts(sentence)
                if audio_data and not self._interrupted:
                    self._audio_queue.append(audio_data)

            except Exception as e:
                _flog(f"[TTS Worker] 异常: {e}")
                time.sleep(0.1)


    def _audio_player(self):
        """音频播放线程：从 Audio Queue 取音频，播放"""
        gen = self._tts_generation  # 启动时的代次
        while self._player_running:
            try:
                # 代次不匹配时退出（新 TTS 已启动）
                if gen != self._tts_generation:
                    _flog(f"[Audio Player] 代次不匹配 (self={gen}, current={self._tts_generation})，退出")
                    break

                # 打断时立即退出
                if self._interrupted:
                    self._drain_audio_queue()
                    break

                # 状态已不是 speaking 时退出
                if self._state != PipelineState.SPEAKING:
                    self._drain_audio_queue()
                    break

                # 从队列取音频
                if not self._audio_queue:
                    time.sleep(0.05)
                    continue

                audio_data = self._audio_queue.popleft()
                if audio_data is None:  # 结束信号
                    break

                # 再次检查打断标志（pop 后可能已被打断）
                if self._interrupted:
                    self._cleanup_audio_file(audio_data)
                    self._drain_audio_queue()
                    break

                finished = self._play_audio(audio_data)
                if not finished:
                    self._drain_audio_queue()
                    break

            except Exception as e:
                _flog(f"[Audio Player] 异常: {e}")
                time.sleep(0.1)

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
                creationflags=subprocess.CREATE_NO_WINDOW,
            )
            self._current_ffplay_proc = proc

            # 轮询等待进程结束，每 100ms 检查打断标志
            while proc.poll() is None:
                if self._interrupted:
                    _flog("[Audio Player] 播放被中断，终止 ffplay")
                    try:
                        subprocess.run(
                            ["taskkill", "/F", "/T", "/PID", str(proc.pid)],
                            capture_output=True, timeout=3,
                            creationflags=subprocess.CREATE_NO_WINDOW,
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
