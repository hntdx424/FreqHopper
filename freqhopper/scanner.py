"""Continuous scan / squelch lock engine."""

from __future__ import annotations

import threading
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from typing import Any

import numpy as np

from freqhopper.audio_player import AudioPlayer
from freqhopper.defaults import (
    DEFAULT_DWELL_MS,
    DEFAULT_GAIN,
    DEFAULT_HANG_MS,
    DEFAULT_HYSTERESIS_DB,
    DEFAULT_MODULATION,
    DEFAULT_PPM,
    DEFAULT_SAMPLE_RATE,
    DEFAULT_SQUELCH_DB,
    DEFAULT_VOLUME,
    FLUSH_SAMPLES,
    LOCK_SAMPLES,
    SCAN_SAMPLES,
)
from freqhopper.demod import Demodulator, power_dbfs
from freqhopper.sdr_device import RtlSdrBackend, SdrBackend, SdrError


@dataclass
class ScanStatus:
    state: str = "idle"
    mode: str = "range"
    frequency_hz: float = 0.0
    signal_db: float = -120.0
    squelch_db: float = DEFAULT_SQUELCH_DB
    squelch_open: bool = False
    device_label: str = "No device"
    message: str = "Idle"
    index: int = 0
    channel_count: int = 0
    audio_ok: bool = True


@dataclass
class RuntimeParams:
    """Values the GUI can change while the scanner is running."""

    squelch_db: float = DEFAULT_SQUELCH_DB
    hysteresis_db: float = DEFAULT_HYSTERESIS_DB
    hang_s: float = DEFAULT_HANG_MS / 1000.0
    dwell_s: float = DEFAULT_DWELL_MS / 1000.0
    volume: float = DEFAULT_VOLUME
    gain: Any = DEFAULT_GAIN
    modulation: str = DEFAULT_MODULATION
    ppm: int = DEFAULT_PPM
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            return {
                "squelch_db": self.squelch_db,
                "hysteresis_db": self.hysteresis_db,
                "hang_s": self.hang_s,
                "dwell_s": self.dwell_s,
                "volume": self.volume,
                "gain": self.gain,
                "modulation": self.modulation,
                "ppm": self.ppm,
            }

    def update(self, **kwargs: Any) -> None:
        with self._lock:
            for key, value in kwargs.items():
                if not hasattr(self, key) or key.startswith("_"):
                    continue
                setattr(self, key, value)


class ScannerEngine:
    def __init__(
        self,
        frequencies_hz: Sequence[float],
        mode: str = "range",
        device_index: int = 0,
        backend: SdrBackend | None = None,
        audio: AudioPlayer | None = None,
        params: RuntimeParams | None = None,
        sample_rate: float = DEFAULT_SAMPLE_RATE,
        scan_samples: int = SCAN_SAMPLES,
        lock_samples: int = LOCK_SAMPLES,
        on_status: Callable[[ScanStatus], None] | None = None,
        on_error: Callable[[str], None] | None = None,
    ) -> None:
        if not frequencies_hz:
            raise SdrError("No frequencies to scan.")
        self.frequencies_hz = [float(f) for f in frequencies_hz]
        self.mode = mode
        self.device_index = device_index
        self.backend = backend or RtlSdrBackend()
        self.audio = audio or AudioPlayer()
        self.params = params or RuntimeParams()
        self.sample_rate = sample_rate
        self.scan_samples = int(scan_samples)
        self.lock_samples = int(lock_samples)
        self.on_status = on_status
        self.on_error = on_error
        self._running = threading.Event()
        self._thread: threading.Thread | None = None
        self._status = ScanStatus(mode=mode, channel_count=len(self.frequencies_hz))
        self._applied_gain: Any = object()

    @property
    def running(self) -> bool:
        return self._running.is_set()

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._running.set()
        self._thread = threading.Thread(target=self._loop, name="freqhopper-scan", daemon=True)
        self._thread.start()

    def stop(self, timeout: float = 3.0) -> None:
        self._running.clear()
        thread = self._thread
        if thread is not None and thread.is_alive():
            thread.join(timeout=timeout)
        self._thread = None

    def _emit(self, **kwargs: Any) -> None:
        snap = self.params.snapshot()
        for key, value in kwargs.items():
            setattr(self._status, key, value)
        self._status.squelch_db = float(snap["squelch_db"])
        self._status.mode = self.mode
        self._status.channel_count = len(self.frequencies_hz)
        self._status.audio_ok = bool(getattr(self.audio, "available", True))
        callback = self.on_status
        if callback is not None:
            callback(self._status)

    def _loop(self) -> None:
        backend = self.backend
        try:
            backend.open(self.device_index)
            snap = self.params.snapshot()
            backend.configure(self.sample_rate, snap["gain"], snap["ppm"])
            self.sample_rate = float(backend.sample_rate)
            self._applied_gain = snap["gain"]
            self.audio.start()
            start_message = "Starting scan…"
            if getattr(self.audio, "error_message", ""):
                start_message = self.audio.error_message
            self._emit(
                state="scanning",
                device_label=backend.label(),
                message=start_message,
                squelch_open=False,
            )
            index = 0
            while self._running.is_set():
                snap = self.params.snapshot()
                self._apply_gain(backend, snap["gain"])
                self.audio.volume = snap["volume"]
                freq = self.frequencies_hz[index]
                self._tune(backend, freq)
                dwell = max(0.0, float(snap["dwell_s"]))
                if dwell:
                    self._sleep(dwell)
                samples = backend.read_samples(self.scan_samples)
                signal = power_dbfs(samples)
                self._emit(
                    state="scanning",
                    frequency_hz=freq,
                    signal_db=signal,
                    squelch_open=False,
                    index=index,
                    device_label=backend.label(),
                    message=f"Scanning {len(self.frequencies_hz)} channels",
                )
                if signal >= float(snap["squelch_db"]):
                    self._hold(freq, samples, index)
                index = (index + 1) % len(self.frequencies_hz)
        except Exception as exc:
            message = str(exc) if str(exc) else exc.__class__.__name__
            self._emit(state="error", squelch_open=False, message=message)
            if self.on_error:
                self.on_error(message)
        finally:
            try:
                self.audio.stop()
            except Exception:
                pass
            try:
                backend.close()
            except Exception:
                pass
            if self._status.state != "error":
                self._emit(state="stopped", squelch_open=False, message="Stopped")

    def _hold(self, freq: float, first_samples: np.ndarray, index: int) -> None:
        snap = self.params.snapshot()
        demod = Demodulator(self.sample_rate, mode=snap["modulation"])
        self.audio.unmute()
        hang_until: float | None = None
        self._play(demod, first_samples, snap["volume"])
        self._emit(
            state="locked",
            frequency_hz=freq,
            signal_db=power_dbfs(first_samples),
            squelch_open=True,
            index=index,
            message=f"Squelch open — holding {freq / 1e6:.3f} MHz",
        )

        while self._running.is_set():
            snap = self.params.snapshot()
            self.audio.volume = snap["volume"]
            self._apply_gain(self.backend, snap["gain"])
            if demod.mode != snap["modulation"]:
                demod = Demodulator(self.sample_rate, mode=snap["modulation"])
            samples = self.backend.read_samples(self.lock_samples)
            signal = power_dbfs(samples)
            self._play(demod, samples, snap["volume"])
            close_level = float(snap["squelch_db"]) - float(snap["hysteresis_db"])
            if signal >= close_level:
                hang_until = None
                self._emit(
                    state="locked",
                    frequency_hz=freq,
                    signal_db=signal,
                    squelch_open=True,
                    index=index,
                    message=f"Squelch open — holding {freq / 1e6:.3f} MHz",
                )
                continue

            now = time.monotonic()
            if hang_until is None:
                hang_until = now + max(0.0, float(snap["hang_s"]))
            remaining = max(0.0, hang_until - now)
            self._emit(
                state="locked",
                frequency_hz=freq,
                signal_db=signal,
                squelch_open=True,
                index=index,
                message=f"Signal dropped — hang {remaining * 1000:.0f} ms",
            )
            if remaining <= 0:
                break

        self.audio.mute()
        self._emit(
            state="scanning",
            frequency_hz=freq,
            squelch_open=False,
            message="Squelch closed — resuming scan",
        )

    def _play(self, demod: Demodulator, samples: np.ndarray, volume: float) -> None:
        audio = demod.process(samples)
        self.audio.volume = volume
        self.audio.play(audio)

    def _tune(self, backend: SdrBackend, freq: float) -> None:
        backend.set_center_freq(freq)
        try:
            backend.read_samples(FLUSH_SAMPLES)
        except Exception:
            pass

    def _apply_gain(self, backend: SdrBackend, gain: Any) -> None:
        if gain == self._applied_gain:
            return
        try:
            backend.set_gain(gain)
            self._applied_gain = gain
        except Exception:
            pass

    def _sleep(self, seconds: float) -> None:
        deadline = time.monotonic() + seconds
        while self._running.is_set() and time.monotonic() < deadline:
            time.sleep(min(0.02, deadline - time.monotonic()))
