#!/usr/bin/env python3
"""Voice Assistant — headless real-time voice interaction + wake word for RK3576.

Architecture:
  Microphone (sounddevice 16kHz) → Silero VAD → Wake Word (STT) →
  Command (STT) → OpenClaw (LLM) → edge-tts → ffplay

Usage:
  python3 voice_assistant.py                    # start interactive
  python3 voice_assistant.py --daemon           # background daemon
  python3 voice_assistant.py --once             # single command mode
"""
from __future__ import annotations
import argparse
import collections
import io
import json
import os
import queue
import re
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

# ── Project modules ──
_SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(_SCRIPT_DIR))

from vad_engine import SileroVAD

# ── Logging ─────────────────────────────────────────────────
_LOG_LINES: list[str] = []


def _log(msg: str):
    ts = time.strftime("%H:%M:%S")
    line = f"[Voice {ts}] {msg}"
    _LOG_LINES.append(line)
    print(line, flush=True)


# ── State Machine ────────────────────────────────────────────
class State(Enum):
    IDLE = auto()
    WAKE_LISTEN = auto()
    COMMAND_LISTEN = auto()
    PROCESSING = auto()
    SPEAKING = auto()


# ── Config ───────────────────────────────────────────────────
@dataclass
class VAConfig:
    sample_rate: int = 16000
    chunk_size: int = 512  # 32ms @ 16kHz
    vad_threshold: float = 0.5
    vad_speaking_threshold: float = 0.8
    wake_word: str = "小爱同学"
    stt_url: str = "http://127.0.0.1:18766/sensevoice/transcribe"
    max_wake_listen: float = 30.0  # max seconds waiting for wake word
    silence_timeout: float = 0.7  # seconds of silence to end command (match voice_pipeline.py)
    max_command: float = 10.0  # max command recording seconds
    wake_check_interval: float = 0.5  # seconds between wake word checks
    mic_device: str = ""  # empty = default; int = device index


def load_config() -> VAConfig:
    cfg = VAConfig()
    settings_path = _SCRIPT_DIR / "settings.json"
    if settings_path.exists():
        try:
            data = json.loads(settings_path.read_text())
            if data.get("wake_word"):
                cfg.wake_word = data["wake_word"]
            if data.get("mic_device") or data.get("mic_device") == 0:
                cfg.mic_device = data["mic_device"]
        except Exception:
            pass
    return cfg


# ── Voice Assistant ──────────────────────────────────────────
class VoiceAssistant:
    """Headless voice assistant with wake word + real-time conversation."""

    def __init__(self, config: VAConfig | None = None):
        self.cfg = config or load_config()
        self.state = State.IDLE
        self.running = False
        self.interrupted = False
        self._pending_wake_checks = 0  # counter for in-flight STT requests

        # Audio buffer — maxlen keeps only recent ~6s of 16kHz int16
        self._audio_buffer: collections.deque[np.ndarray] = collections.deque(maxlen=190)
        self._command_buffer: collections.deque[np.ndarray] = collections.deque(maxlen=190)
        self._buffer_start_time = 0.0

        # VAD
        _log("Loading Silero VAD...")
        self.vad = SileroVAD()
        self._last_speech_time = 0.0

        # Audio stream
        self._stream: sd.InputStream | None = None
        self._chunk_queue: queue.Queue[np.ndarray] = queue.Queue()

        # TTS
        self._tts_process: subprocess.Popen | None = None

        # Session
        self._session_key = ""  # use default main session
        self._wake_text = ""  # the text that triggered wake word detection
        self._llm_queue: queue.Queue[tuple[str, str]] = queue.Queue()

    # ── Audio Callback ────────────────────────────────────
    def _audio_callback(self, indata: np.ndarray, frames: int, time_info, status):
        if status:
            _log(f"Audio status: {status}")
        self._chunk_queue.put(indata.copy().flatten())

    # ── Start / Stop ──────────────────────────────────────
    def start(self):
        if self.running:
            return
        self.running = True
        self.state = State.IDLE

        mic_dev: int | None = 0  # ALSA hw:0,0 (ES8383 — only working mic on RK3576)
        if self.cfg.mic_device != "":
            try:
                mic_dev = int(self.cfg.mic_device)
            except (ValueError, TypeError):
                try:
                    for d in sd.query_devices():
                        if self.cfg.mic_device in d["name"]:
                            mic_dev = d["index"]
                            break
                except Exception:
                    mic_dev = 0

        self._stream = sd.InputStream(
            samplerate=self.cfg.sample_rate,
            channels=1,
            dtype="int16",
            blocksize=self.cfg.chunk_size,
            device=mic_dev,
            callback=self._audio_callback,
        )
        self._stream.start()
        _log(f"Mic started (device={mic_dev or 'default'}, sr={self.cfg.sample_rate})")
        _log(f"Wake word: '{self.cfg.wake_word}' | State: IDLE")

        # Main loop
        try:
            while self.running:
                try:
                    chunk = self._chunk_queue.get(timeout=0.1)
                    # Discard audio during processing/speaking to prevent feedback
                    if self.state in (State.PROCESSING, State.SPEAKING):
                        # Drain excess chunks to prevent overflow
                        while not self._chunk_queue.empty():
                            try:
                                self._chunk_queue.get_nowait()
                            except queue.Empty:
                                break
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
        self._interrupt()

    def _cleanup(self):
        self.running = False
        if self._stream:
            self._stream.stop()
            self._stream.close()
        self._interrupt()
        _log("Stopped")

    # ── State Machine ─────────────────────────────────────
    def _process_chunk(self, chunk: np.ndarray):
        now = time.time()
        # VAD
        audio_f32 = chunk.astype(np.float32) / 32768.0
        prob = self.vad(audio_f32, self.cfg.sample_rate)

        if self.state == State.IDLE:
            if prob > self.cfg.vad_threshold:
                _log("Speech detected → WAKE_LISTEN")
                self.state = State.WAKE_LISTEN
                self._audio_buffer.clear()
                self._command_buffer.clear()
                self._buffer_start_time = now
                self._last_speech_time = now
                self._last_wake_check = 0  # reset for new cycle
                self._audio_buffer.append(chunk.copy())
            return

        if self.state == State.WAKE_LISTEN:
            self._audio_buffer.append(chunk.copy())
            if prob > self.cfg.vad_threshold:
                self._last_speech_time = now

            elapsed = now - self._buffer_start_time
            silence_dur = now - self._last_speech_time

            # Timeout? Pending STT blocks silence timeout (3s like voice_pipeline.py)
            if elapsed > self.cfg.max_wake_listen:
                _log("Wake listen max time → IDLE")
                self.state = State.IDLE
                return
            if silence_dur > 3.0 and self._pending_wake_checks == 0:
                _log("Wake listen timeout → IDLE")
                self.state = State.IDLE
                return

            # Check wake word periodically (non-blocking: run in thread)
            if elapsed >= 0.8 and elapsed - self._last_wake_check >= self.cfg.wake_check_interval:
                self._last_wake_check = now
                import copy
                buf_snapshot = copy.deepcopy(self._audio_buffer)
                dur = sum(len(c) for c in buf_snapshot) / self.cfg.sample_rate
                _log(f"Wake check dispatch: buf={dur:.1f}s, elapsed={elapsed:.1f}s")
                self._pending_wake_checks += 1
                threading.Thread(
                    target=self._check_wake_word_async,
                    args=(buf_snapshot,),
                    daemon=True,
                ).start()

            return

        if self.state == State.COMMAND_LISTEN:
            self._command_buffer.append(chunk.copy())
            if prob > self.cfg.vad_threshold:
                self._last_speech_time = now

            elapsed = now - self._buffer_start_time
            silence_dur = now - self._last_speech_time

            if silence_dur > self.cfg.silence_timeout or elapsed > self.cfg.max_command:
                _log(f"Command end (elapsed={elapsed:.1f}s, silence={silence_dur:.1f}s)")
                self.state = State.PROCESSING
                threading.Thread(target=self._process_command, daemon=True).start()
            return

        if self.state == State.SPEAKING:
            if prob > self.cfg.vad_speaking_threshold:
                _log("Interrupted by speech")
                self._interrupt()
                self.state = State.IDLE
            return

    # ── Wake Word Detection ───────────────────────────────
    def _check_wake_word_async(self, buf_snapshot):
        """Run in background thread — transcribe snapshot, update state if matched."""
        try:
            text = self._transcribe_buffer(buf_snapshot)
            self._pending_wake_checks -= 1
            if not text:
                return

            _log(f"Wake check: '{text}'")
            # Only act if still in WAKE_LISTEN state
            if self.state != State.WAKE_LISTEN:
                return

            ww = self.cfg.wake_word
            if text.startswith(ww) or ww in text:
                _log(f"*** WAKE WORD DETECTED: '{text}' ***")
                self._wake_text = text  # save for command stripping
                self.state = State.COMMAND_LISTEN
                self._command_buffer.clear()
                self._buffer_start_time = time.time()
                self._last_speech_time = time.time()
                self._command_buffer.extend(self._audio_buffer)
            elif len(text) >= 2:
                # Fuzzy: check 2-char overlap
                for i in range(len(ww) - 1):
                    sub = ww[i : i + 2]
                    if sub in text:
                        _log(f"Wake word fuzzy match ({sub}) → COMMAND_LISTEN")
                        self._wake_text = text  # save for command stripping
                        self.state = State.COMMAND_LISTEN
                        self._command_buffer.clear()
                        self._command_buffer.extend(self._audio_buffer)
                        self._buffer_start_time = time.time()
                        self._last_speech_time = time.time()
                        return
        except Exception as e:
            self._pending_wake_checks -= 1
            _log(f"Wake check error: {e}")

    # ── Command Processing ─────────────────────────────────
    def _process_command(self):
        try:
            text = self._transcribe_buffer(self._command_buffer)
            if not text:
                _log("Command: no speech detected")
                self.state = State.IDLE
                return

            # Strip wake word from command (use both configured and actual detected text)
            ww = self.cfg.wake_word
            wt = self._wake_text  # e.g. "同学" instead of "小爱同学"
            # Try stripping actual detected wake text first
            if wt and wt in text:
                idx = text.index(wt)
                text = text[:idx] + text[idx + len(wt):]
                text = text.strip()
            elif text.startswith(ww):
                text = text[len(ww):].strip()
            # Remove leading punctuation
            text = text.lstrip("，。！？,.!? ")

            _log(f"Command: '{text}'")

            # Call OpenClaw
            self.state = State.PROCESSING
            response = self._llm_chat(text)

            if response:
                _log(f"Final response: {response}")
                # TTS disabled — no speaker output on this board
                # self.state = State.SPEAKING
                # self._tts_speak(response)

            self.state = State.IDLE
        except Exception as e:
            _log(f"Command error: {e}")
            traceback.print_exc()
            self.state = State.IDLE

    # ── STT (SenseVoiceSmall via iflyVoice) ─────────────────
    def _transcribe_buffer(self, buf: collections.deque[np.ndarray]) -> str:
        """Convert PCM buffer to webm, send to STT, return text."""
        if not buf:
            return ""
        try:
            # Concatenate all chunks
            audio = np.concatenate(list(buf)).astype(np.int16)
            buf.clear()
            dur = len(audio) / self.cfg.sample_rate

            if dur < 0.5:  # < 0.5s — too short for SenseVoiceSmall
                _log(f"STT: too short ({dur:.1f}s), skipping")
                return ""

            # Convert to Opus WebM via ffmpeg (matches voice_pipeline.py — better STT accuracy)
            pcm_data = audio.tobytes()
            ffmpeg = subprocess.run(
                ["ffmpeg", "-y", "-f", "s16le", "-ar", str(self.cfg.sample_rate),
                 "-ac", "1", "-i", "pipe:0", "-c:a", "libopus", "-b:a", "32k",
                 "-f", "webm", "pipe:1"],
                input=pcm_data, capture_output=True, timeout=5,
            )
            if ffmpeg.returncode != 0 or len(ffmpeg.stdout) < 100:
                _log(f"STT: ffmpeg failed, falling back to WAV")
                wav_bytes = io.BytesIO()
                self._save_wav_bytes(audio, wav_bytes)
                stt_data = wav_bytes.getvalue()
                filename = "audio.wav"
                content_type = "audio/wav"
            else:
                stt_data = ffmpeg.stdout
                filename = "audio.webm"
                content_type = "audio/webm"

            # Send to STT
            import urllib.request
            import uuid

            _log(f"STT: sending {dur:.1f}s audio to SenseVoiceSmall...")
            boundary = "----Stt" + uuid.uuid4().hex[:16]
            crlf = b"\r\n"
            parts = [
                b"--" + boundary.encode(),
                f'Content-Disposition: form-data; name="file"; filename="{filename}"'.encode(),
                f"Content-Type: {content_type}".encode(),
                b"",
                stt_data,
                b"--" + boundary.encode() + b"--",
            ]
            body = crlf.join(parts)

            req = urllib.request.Request(
                self.cfg.stt_url,
                data=body,
                headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
                method="POST",
            )
            t0 = time.time()
            with urllib.request.urlopen(req, timeout=30) as resp:
                result = json.loads(resp.read().decode())
                text = result.get("text", "").strip()
            _log(f"STT response: '{text}' ({time.time()-t0:.1f}s)")

            return text
        except Exception as e:
            _log(f"STT error: {e}")
            return ""

    def _save_wav_bytes(self, audio: np.ndarray, buf: io.BytesIO):
        import wave
        with wave.open(buf, "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(self.cfg.sample_rate)
            w.writeframes(audio.tobytes())

    # ── LLM (OpenClaw) ────────────────────────────────────
    def _llm_chat(self, text: str) -> str:
        _log(f"LLM: sending to OpenClaw (agent=main)")
        try:
            result = subprocess.run(
                ["openclaw", "agent", "--agent", "main",
                 "--json",
                 "--message", text],
                capture_output=True, text=True, timeout=120,
                env={
                    **os.environ,
                    "OPENCLAW_NO_COLOR": "1",
                    "DISPLAY": "",         # suppress GUI windows
                    "WAYLAND_DISPLAY": "",  # suppress Wayland windows
                    "NO_AT_BRIDGE": "1",   # suppress accessibility bridge
                },
            )
            output = result.stdout.strip()
            # Try JSON first (with --json flag)
            try:
                data = json.loads(output)
                response = data.get("response", "") or data.get("text", "") or output
            except (json.JSONDecodeError, TypeError):
                # Plain text: filter status lines
                lines = [l for l in output.split("\n")
                         if l.strip() and not l.startswith("[")]
                response = "\n".join(lines).strip()
            _log(f"LLM response: {response[:100]}...")
            return response
        except subprocess.TimeoutExpired:
            _log("LLM timeout")
            return "抱歉，响应超时了，请重试。"
        except Exception as e:
            _log(f"LLM error: {e}")
            return f"出错: {e}"

    # ── TTS (edge-tts) ────────────────────────────────────
    def _tts_speak(self, text: str):
        if not text:
            return
        _log(f"TTS: speaking ({len(text)} chars)")
        try:
            with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as f:
                mp3_path = f.name

            subprocess.run(
                ["edge-tts", "--text", text, "--voice", "zh-CN-XiaoxiaoNeural",
                 "--write-media", mp3_path],
                capture_output=True, timeout=30,
                env={**os.environ, "PATH": os.environ.get("PATH", "") + ":/home/cat/.local/bin"},
            )

            if os.path.exists(mp3_path) and os.path.getsize(mp3_path) > 100:
                self._tts_process = subprocess.Popen(
                    ["ffplay", "-nodisp", "-autoexit", "-loglevel", "quiet", mp3_path],
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                )
                self._tts_process.wait(timeout=60)
            else:
                _log("TTS: empty audio output")

            try:
                os.unlink(mp3_path)
            except OSError:
                pass
        except Exception as e:
            _log(f"TTS error: {e}")

    # ── Interrupt ─────────────────────────────────────────
    def _interrupt(self):
        if self._tts_process and self._tts_process.poll() is None:
            _log("Interrupting TTS playback")
            self._tts_process.terminate()
            try:
                self._tts_process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                self._tts_process.kill()


# ── Main ─────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(description="Voice Assistant for RK3576")
    parser.add_argument("--daemon", action="store_true", help="Run as background daemon")
    parser.add_argument("--once", action="store_true", help="Single command mode (no wake word)")
    parser.add_argument("--wake-word", type=str, help="Override wake word")
    args = parser.parse_args()

    config = load_config()
    if args.wake_word:
        config.wake_word = args.wake_word

    va = VoiceAssistant(config)

    if args.once:
        _log("Single command mode — recording 5s...")
        audio_chunks = []
        stream = sd.InputStream(
            samplerate=config.sample_rate, channels=1,
            dtype="int16", blocksize=config.chunk_size, device=0,
        )
        stream.start()
        start = time.time()
        while time.time() - start < 5:
            chunk, _ = stream.read(config.chunk_size)
            audio_chunks.append(chunk.flatten())
        stream.stop()
        stream.close()

        buf = collections.deque(audio_chunks)
        text = va._transcribe_buffer(buf)
        print(f"Recognized: {text}")
        if text:
            response = va._llm_chat(text)
            print(f"Response: {response}")
        return

    # Signal handling
    signal.signal(signal.SIGINT, lambda s, f: va.stop())
    signal.signal(signal.SIGTERM, lambda s, f: va.stop())

    if args.daemon:
        # Daemon mode: write PID and redirect output to log
        log_path = "/tmp/voice_assistant.log"
        pid = os.getpid()
        with open("/tmp/voice_assistant.pid", "w") as f:
            f.write(str(pid))
        _log(f"Daemon mode (pid={pid}), log: {log_path}")
        sys.stdout = open(log_path, "a")
        sys.stderr = sys.stdout

    va.start()


if __name__ == "__main__":
    main()
