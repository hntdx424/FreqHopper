"""Squelch-gated audio playback."""

from __future__ import annotations

import queue
import threading
from collections.abc import Callable

import numpy as np

from freqhopper.defaults import AUDIO_SAMPLE_RATE


class AudioPlayer:
    """Play float32 mono audio only while squelch is open."""

    def __init__(self, samplerate: int = AUDIO_SAMPLE_RATE, on_error: Callable[[str], None] | None = None):
        self.samplerate = samplerate
        self.on_error = on_error
        self.available = False
        self.error_message = ""
        self._queue: queue.Queue[np.ndarray] = queue.Queue(maxsize=12)
        self._leftover = np.zeros(0, dtype=np.float32)
        self._open = False
        self._lock = threading.Lock()
        self._stream = None
        self._volume = 1.0

    @property
    def volume(self) -> float:
        return self._volume

    @volume.setter
    def volume(self, value: float) -> None:
        self._volume = float(np.clip(value, 0.0, 1.5))

    def start(self) -> None:
        self.error_message = ""
        try:
            import sounddevice as sd
        except Exception as exc:  # pragma: no cover - depends on host audio
            self.available = False
            self.error_message = f"Audio library unavailable: {exc}"
            self._notify()
            return

        try:
            self._stream = sd.OutputStream(
                samplerate=self.samplerate,
                channels=1,
                dtype="float32",
                callback=self._callback,
                blocksize=2048,
            )
            self._stream.start()
            self.available = True
        except Exception as exc:  # pragma: no cover - depends on host audio
            self.available = False
            self._stream = None
            self.error_message = (
                "No audio output device is available. Scanning will still work; "
                f"playback is muted. ({exc})"
            )
            self._notify()

    def stop(self) -> None:
        self.mute()
        stream = self._stream
        self._stream = None
        if stream is not None:
            try:
                stream.stop()
                stream.close()
            except Exception:
                pass
        self._drain()

    def unmute(self) -> None:
        with self._lock:
            self._open = True

    def mute(self) -> None:
        with self._lock:
            self._open = False
        self._drain()
        self._leftover = np.zeros(0, dtype=np.float32)

    @property
    def squelch_open(self) -> bool:
        with self._lock:
            return self._open

    def play(self, samples: np.ndarray) -> None:
        if not self.available:
            return
        with self._lock:
            opened = self._open
        if not opened:
            return
        block = np.asarray(samples, dtype=np.float32).reshape(-1)
        if block.size == 0:
            return
        block = np.clip(block * self._volume, -1.0, 1.0)
        try:
            self._queue.put_nowait(block)
        except queue.Full:
            try:
                self._queue.get_nowait()
            except queue.Empty:
                pass
            try:
                self._queue.put_nowait(block)
            except queue.Full:
                pass

    def _drain(self) -> None:
        while True:
            try:
                self._queue.get_nowait()
            except queue.Empty:
                break

    def _callback(self, outdata, frames, _time_info, _status) -> None:
        with self._lock:
            opened = self._open
        if not opened:
            outdata.fill(0)
            return

        out = np.zeros(frames, dtype=np.float32)
        n = 0
        leftover = self._leftover
        if leftover.size:
            take = min(leftover.size, frames)
            out[:take] = leftover[:take]
            leftover = leftover[take:]
            n = take

        while n < frames:
            try:
                chunk = self._queue.get_nowait()
            except queue.Empty:
                break
            need = frames - n
            if chunk.size <= need:
                out[n : n + chunk.size] = chunk
                n += chunk.size
            else:
                out[n:] = chunk[:need]
                leftover = chunk[need:]
                n = frames
                break

        self._leftover = leftover
        outdata[:, 0] = out

    def _notify(self) -> None:
        if self.on_error and self.error_message:
            self.on_error(self.error_message)
