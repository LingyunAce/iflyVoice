#!/usr/bin/env python3
"""Voice Assistant v2 — simplified: record full utterance → STT once → check wake word.

Key change from v1: no more multi-shot wake word checks with short audio clips.
Instead, record the complete utterance, transcribe it once with full context,
then check if it starts with the wake word. This matches how voice_input.sh
works and dramatically improves STT accuracy with weak microphones.

Usage:
  python3 voice_assistant.py                 # interactive mode
  python3 voice_assistant.py --daemon        # background daemon
  python3 voice_assistant.py --once          # single command mode
"""
from __future__ import annotations
import argparse
import collections
import io
import json
import os
import queue
import signal
import subprocess
import sys
import tempfile
import threading
import time
import traceback
from dataclasses import dataclass
from enum import Enum, auto
from pathlib import Path

import numpy as np
import sounddevice as sd

_SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(_SCRIPT_DIR))
from vad_engine import SileroVAD

# ── Logging ─────────────────────────────────────────────────
_LOG_LINES: list[str] = []

def _log(msg: str):
    line = f"[Voice {time.strftime('%H:%M:%S')}] {msg}"
    _LOG_LINES.append(line)
    print(line, flush=True)

# ── State Machine ────────────────────────────────────────────
class State(Enum):
    IDLE = auto()
    LISTENING = auto()    # recording full utterance
    PROCESSING = auto()   # STT → wake check → LLM

@dataclass
class VAConfig:
    sample_rate: int = 16000
    chunk_size: int = 512
    vad_threshold: float = 0.5
    wake_word: str = "小助手"
    stt_url: str = "http://127.0.0.1:18766/sensevoice/transcribe"
    silence_timeout: float = 1.2  # silence to end utterance
    max_utterance: float = 12.0   # max recording seconds
    mic_device: str = ""

def load_config() -> VAConfig:
    cfg = VAConfig()
    settings_path = _SCRIPT_DIR / "settings.json"
    if settings_path.exists():
        try:
            data = json.loads(settings_path.read_text())
            if data.get("wake_word"):
                cfg.wake_word = data["wake_word"]
            if data.get("mic_device"):
                cfg.mic_device = str(data["mic_device"])
        except Exception:
            pass
    return cfg

# ── Voice Assistant ──────────────────────────────────────────
class VoiceAssistant:

    def __init__(self, config: VAConfig | None = None):
        self.cfg = config or load_config()
        self.state = State.IDLE
        self.running = False

        # Audio buffer + pre-buffer (catches speech before VAD trigger)
        self._audio_buffer: collections.deque[np.ndarray] = collections.deque(maxlen=400)
        self._pre_buffer: collections.deque[np.ndarray] = collections.deque(maxlen=16)  # ~0.5s
        self._buffer_start_time = 0.0
        self._last_speech_time = 0.0

        # VAD
        _log("Loading Silero VAD...")
        self.vad = SileroVAD()

        # Audio stream
        self._stream: sd.InputStream | None = None
        self._chunk_queue: queue.Queue[np.ndarray] = queue.Queue()

        # Session
        self._session_id = f"va-{int(time.time())}"

    # ── Audio Callback ────────────────────────────────────
    def _audio_callback(self, indata: np.ndarray, frames: int, time_info, status):
        if status:
            return  # don't log overflow during processing
        self._chunk_queue.put(indata.copy().flatten())

    # ── Start / Stop ──────────────────────────────────────
    def start(self):
        if self.running:
            return
        self.running = True
        self.state = State.IDLE

        mic_dev: int | None = 0  # ALSA hw:0,0
        if self.cfg.mic_device:
            try:
                mic_dev = int(self.cfg.mic_device)
            except (ValueError, TypeError):
                mic_dev = 0

        self._stream = sd.InputStream(
            samplerate=self.cfg.sample_rate, channels=1,
            dtype="int16", blocksize=self.cfg.chunk_size,
            device=mic_dev, callback=self._audio_callback,
        )
        self._stream.start()
        _log(f"v2 started (mic={mic_dev}, wake_word='{self.cfg.wake_word}') | State: IDLE")

        try:
            while self.running:
                try:
                    chunk = self._chunk_queue.get(timeout=0.1)
                    # Drain during processing
                    if self.state == State.PROCESSING:
                        while not self._chunk_queue.empty():
                            try: self._chunk_queue.get_nowait()
                            except queue.Empty: break
                        continue
                    self._process_chunk(chunk)
                except queue.Empty:
                    continue
        except KeyboardInterrupt:
            _log("Interrupted")
        finally:
            self._cleanup()

    def stop(self):
        _log("Stopping...")
        self.running = False

    def _cleanup(self):
        self.running = False
        if self._stream:
            self._stream.stop()
            self._stream.close()
        _log("Stopped")

    # ── State Machine ─────────────────────────────────────
    def _process_chunk(self, chunk: np.ndarray):
        now = time.time()
        prob = self.vad(chunk.astype(np.float32) / 32768.0, self.cfg.sample_rate)

        if self.state == State.IDLE:
            # Always keep pre-buffer of last ~0.5s audio
            self._pre_buffer.append(chunk.copy())
            if prob > self.cfg.vad_threshold:
                _log("Speech detected → LISTENING")
                self.state = State.LISTENING
                self._audio_buffer.clear()
                # Prepend pre-buffer to catch beginning of wake word
                self._audio_buffer.extend(self._pre_buffer)
                self._pre_buffer.clear()
                self._buffer_start_time = now
                self._last_speech_time = now
            return

        if self.state == State.LISTENING:
            self._audio_buffer.append(chunk.copy())
            if prob > self.cfg.vad_threshold:
                self._last_speech_time = now

            elapsed = now - self._buffer_start_time
            silence = now - self._last_speech_time

            if silence > self.cfg.silence_timeout or elapsed > self.cfg.max_utterance:
                dur = sum(len(c) for c in self._audio_buffer) / self.cfg.sample_rate
                _log(f"Utterance end: {dur:.1f}s → PROCESSING")
                self.state = State.PROCESSING
                buf = self._audio_buffer
                self._audio_buffer = collections.deque(maxlen=400)
                threading.Thread(target=self._process_utterance, args=(buf,), daemon=True).start()
            return

    # ── Utterance Processing ──────────────────────────────
    def _process_utterance(self, buf: collections.deque[np.ndarray]):
        try:
            text = self._transcribe(buf)
            if not text:
                _log("No speech recognized → IDLE")
                self.state = State.IDLE
                return

            _log(f"Recognized: '{text}'")
            ww = self.cfg.wake_word

            # Check if starts with or contains wake word
            if text.startswith(ww):
                command = text[len(ww):].strip().lstrip("，。！？,.!? ")
            elif ww in text:
                idx = text.index(ww)
                command = (text[:idx] + text[idx + len(ww):]).strip().lstrip("，。！？,.!? ")
            else:
                # Fuzzy: check 2-char overlap
                matched = False
                for i in range(len(ww) - 1):
                    if ww[i:i+2] in text:
                        _log(f"Fuzzy wake match: '{ww[i:i+2]}'")
                        matched = True
                        # Try to strip
                        idx = text.index(ww[i:i+2])
                        command = (text[:idx] + text[idx+2:]).strip().lstrip("，。！？,.!? ")
                        break
                if not matched:
                    _log("No wake word match → IDLE")
                    self.state = State.IDLE
                    return

            if not command:
                _log("Wake word only (no command) → IDLE")
                self.state = State.IDLE
                return

            _log(f"Command: '{command}'")
            response = self._llm_chat(command)
            if response:
                _log(f"Response: {response[:100]}...")
            self.state = State.IDLE

        except Exception as e:
            _log(f"Process error: {e}")
            traceback.print_exc()
            self.state = State.IDLE

    # ── STT ───────────────────────────────────────────────
    def _transcribe(self, buf: collections.deque[np.ndarray]) -> str:
        if not buf:
            return ""
        try:
            audio = np.concatenate(list(buf)).astype(np.int16)
            dur = len(audio) / self.cfg.sample_rate

            if dur < 0.5:
                _log(f"STT: too short ({dur:.1f}s)")
                return ""

            # WAV bytes (matches voice_input.sh proven path)
            wav_buf = io.BytesIO()
            self._save_wav_bytes(audio, wav_buf)
            wav_data = wav_buf.getvalue()

            import urllib.request, uuid

            _log(f"STT: sending {dur:.1f}s → SenseVoiceSmall")
            boundary = "----Stt" + uuid.uuid4().hex[:16]
            crlf = b"\r\n"
            parts = [
                b"--" + boundary.encode(),
                b'Content-Disposition: form-data; name="file"; filename="audio.wav"',
                b"Content-Type: audio/wav",
                b"", wav_data,
                b"--" + boundary.encode() + b"--",
            ]
            body = crlf.join(parts)
            req = urllib.request.Request(
                self.cfg.stt_url, data=body,
                headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
                method="POST",
            )
            t0 = time.time()
            with urllib.request.urlopen(req, timeout=30) as resp:
                result = json.loads(resp.read().decode())
                text = result.get("text", "").strip()
            _log(f"STT: '{text}' ({time.time()-t0:.1f}s)")
            return text
        except Exception as e:
            _log(f"STT error: {e}")
            return ""

    def _save_wav_bytes(self, audio: np.ndarray, buf: io.BytesIO):
        import wave
        with wave.open(buf, "wb") as w:
            w.setnchannels(1); w.setsampwidth(2)
            w.setframerate(self.cfg.sample_rate)
            w.writeframes(audio.tobytes())

    # ── LLM (OpenClaw) ────────────────────────────────────
    def _llm_chat(self, text: str) -> str:
        _log(f"LLM → OpenClaw")
        try:
            result = subprocess.run(
                ["openclaw", "agent", "--agent", "main", "--json", "--message", text],
                capture_output=True, text=True, timeout=120,
                env={**os.environ, "OPENCLAW_NO_COLOR": "1",
                     "DISPLAY": "", "WAYLAND_DISPLAY": ""},
            )
            output = result.stdout.strip()
            try:
                data = json.loads(output)
                response = data.get("response", "") or data.get("text", "") or output
            except (json.JSONDecodeError, TypeError):
                lines = [l for l in output.split("\n") if l.strip() and not l.startswith("[")]
                response = "\n".join(lines).strip()
            _log(f"LLM: {response[:100]}...")
            return response
        except subprocess.TimeoutExpired:
            _log("LLM timeout")
            return "抱歉，响应超时。"
        except Exception as e:
            _log(f"LLM error: {e}")
            return f"出错: {e}"

# ── Main ─────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(description="Voice Assistant v2 for RK3576")
    parser.add_argument("--daemon", action="store_true")
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--wake-word", type=str)
    args = parser.parse_args()

    config = load_config()
    if args.wake_word:
        config.wake_word = args.wake_word

    va = VoiceAssistant(config)

    if args.once:
        _log("Recording 5s...")
        stream = sd.InputStream(
            samplerate=config.sample_rate, channels=1,
            dtype="int16", blocksize=config.chunk_size, device=0,
        )
        stream.start()
        chunks = []
        for _ in range(int(config.sample_rate / config.chunk_size * 5)):
            data, _ = stream.read(config.chunk_size)
            chunks.append(data.flatten())
        stream.stop(); stream.close()
        buf = collections.deque(chunks, maxlen=400)
        text = va._transcribe(buf)
        print(f"Recognized: '{text}'")
        if text:
            response = va._llm_chat(text)
            print(f"Response: {response[:200]}...")
        return

    signal.signal(signal.SIGINT, lambda s, f: va.stop())
    signal.signal(signal.SIGTERM, lambda s, f: va.stop())

    if args.daemon:
        log_path = "/tmp/voice_assistant.log"
        pid = os.getpid()
        with open("/tmp/voice_assistant.pid", "w") as f:
            f.write(str(pid))
        _log(f"Daemon (pid={pid})")
        sys.stdout = open(log_path, "a")
        sys.stderr = sys.stdout

    va.start()

if __name__ == "__main__":
    main()
