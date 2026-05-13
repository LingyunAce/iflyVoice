#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
常开麦克风语音管线：VAD → 唤醒词检测 → 语音识别 → LLM
"""
import sys, os, json, time, threading, tempfile, uuid, subprocess, http.client, collections
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

        # 线程
        self._audio_thread = None
        self._worker_thread = None
        self._running = False
        self._stream = None

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

    def notify_tts_done(self):
        """TTS 播放完成，恢复监听"""
        if self._state == PipelineState.SPEAKING:
            self._set_state(PipelineState.IDLE)

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
            self._stream = sd.InputStream(
                samplerate=self._sample_rate,
                channels=1,
                dtype='int16',
                blocksize=self._chunk_size,
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

        # 暂停或 TTS 播放中：忽略音频
        if state in (PipelineState.PAUSED, PipelineState.SPEAKING, PipelineState.PROCESSING):
            return

        # 计算 VAD 概率
        vad_prob = self._get_vad_prob(chunk)

        if state == PipelineState.IDLE:
            if vad_prob >= self._vad_threshold:
                _flog(f"[VAD] 检测到语音 prob={vad_prob:.2f}")
                self._speech_buffer = bytearray()
                self._silence_frames = 0
                self._append_to_buffer(chunk)
                self._set_state(PipelineState.WAKE_LISTEN)

        elif state == PipelineState.WAKE_LISTEN:
            self._append_to_buffer(chunk)

            if vad_prob >= self._vad_threshold:
                self._silence_frames = 0
            else:
                self._silence_frames += 1

            # 检查唤醒词（每 ~1秒检查一次，给 ASR 足够的音频）
            # 使用 ASR 检测，需要至少 1 秒的音频
            check_interval = int(self._sample_rate * 1.0 * 2)  # 1秒的 int16 数据
            if len(self._speech_buffer) >= check_interval and len(self._speech_buffer) % check_interval < self._chunk_size * 2:
                if self._check_wake_word():
                    _flog(f"[唤醒] 唤醒词命中: {self._wake_word}")
                    self.wake_word_detected.emit(self._wake_word)
                    # 保留已缓冲的音频（唤醒词后面的可能是指令）
                    self._silence_frames = 0
                    self._set_state(PipelineState.COMMAND_LISTEN)
                    return

            # 静音超时：无唤醒词，回退到 IDLE
            if self._silence_frames * (self._chunk_size / self._sample_rate * 1000) >= self._silence_timeout_ms:
                _flog("[唤醒] 静音超时，无唤醒词")
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
        # 当音频积累到足够长度时（~1秒），用 ASR 检测唤醒词
        min_bytes = int(self._sample_rate * 1.0 * 2)  # 1秒的 int16 数据
        if len(self._speech_buffer) < min_bytes:
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

            return False

        except Exception as e:
            _flog(f"[唤醒] ASR 检测异常: {e}")
            return False

    def _process_command(self, pcm_data):
        """Worker 线程：ASR + LLM"""
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
            self.command_captured.emit(text)

            # 3. LLM
            self._chat_with_llm(text)

        except Exception as e:
            _flog(f"[处理] 异常: {e}")
            self.error_occurred.emit(str(e))
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

    def _chat_with_llm(self, text):
        """流式请求 LLM，发射信号"""
        try:
            # 预检
            try:
                pre = Request(f"{self._server_url}/ollama/api/tags",
                              headers={"Content-Type": "application/json"})
                urlopen(pre, timeout=3).close()
            except Exception as e:
                _flog(f"[LLM] 预检失败: {e}")
                self.error_occurred.emit(f"AI 服务不可达: {e}")
                self._set_state(PipelineState.IDLE)
                return

            payload = json.dumps({
                "model": "qwen3-vl:4b",
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
            while True:
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
                            if token_count % 5 == 0 or token_count == 1:
                                self.ai_response_stream.emit(full)
                    except json.JSONDecodeError:
                        continue

            resp.close()
            _flog(f"[LLM] 完成 tokens={token_count} len={len(full)}")
            self.ai_response_done.emit(full)

        except Exception as e:
            _flog(f"[LLM] 错误: {e}")
            self.error_occurred.emit(str(e))
            self._set_state(PipelineState.IDLE)
