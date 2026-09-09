"""IQ power measurement and analog demodulation."""

from __future__ import annotations

import numpy as np
from scipy.signal import butter, lfilter, resample_poly

from freqhopper.defaults import AUDIO_SAMPLE_RATE

MODULATION_MODES = ("nbfm", "wbfm", "am")

_MODE_LABELS = {
    "nbfm": "NBFM (narrow FM)",
    "wbfm": "WBFM (broadcast FM)",
    "am": "AM",
}


def modulation_choices() -> list[tuple[str, str]]:
    return [(key, _MODE_LABELS[key]) for key in MODULATION_MODES]


def power_dbfs(samples: np.ndarray) -> float:
    """Mean-square power of complex IQ samples in dBFS."""
    if samples.size == 0:
        return -120.0
    power = float(np.mean(np.real(samples) ** 2 + np.imag(samples) ** 2))
    if power <= 1e-20:
        return -120.0
    return 10.0 * np.log10(power)


def _butter_lowpass(cutoff_hz: float, fs: float, order: int = 5):
    nyq = fs * 0.5
    norm = min(max(cutoff_hz / nyq, 1e-4), 0.99)
    return butter(order, norm, btype="low")


def _decimate_complex(iq: np.ndarray, factor: int, z_i, z_q, cutoff_hz: float, fs: float):
    if factor <= 1:
        return iq, z_i, z_q
    b, a = _butter_lowpass(cutoff_hz, fs)
    i, z_i = lfilter(b, a, np.real(iq), zi=z_i)
    q, z_q = lfilter(b, a, np.imag(iq), zi=z_q)
    return (i[::factor] + 1j * q[::factor]).astype(np.complex64), z_i, z_q


def _init_zi(order: int = 5) -> np.ndarray:
    return np.zeros(order, dtype=np.float64)


class Demodulator:
    """Stateful demodulator so filter memory survives across USB blocks."""

    def __init__(self, sample_rate: float, mode: str = "nbfm", audio_rate: int = AUDIO_SAMPLE_RATE):
        if mode not in MODULATION_MODES:
            raise ValueError(f"Unsupported modulation: {mode}")
        self.sample_rate = float(sample_rate)
        self.mode = mode
        self.audio_rate = int(audio_rate)
        self._prev = np.complex64(0)
        self._deemph_y = 0.0
        self._dc_x = 0.0
        self._dc_y = 0.0
        self._zi_i = _init_zi()
        self._zi_q = _init_zi()
        self._zi_audio = _init_zi()

    def reset(self) -> None:
        self._prev = np.complex64(0)
        self._deemph_y = 0.0
        self._dc_x = 0.0
        self._dc_y = 0.0
        self._zi_i = _init_zi()
        self._zi_q = _init_zi()
        self._zi_audio = _init_zi()

    def process(self, iq: np.ndarray) -> np.ndarray:
        if iq.size < 8:
            return np.zeros(0, dtype=np.float32)
        iq = np.asarray(iq, dtype=np.complex64)
        if self.mode == "am":
            audio = self._demod_am(iq)
        else:
            audio = self._demod_fm(iq, wide=self.mode == "wbfm")
        audio = self._dc_block(audio)
        audio = self._limit(audio)
        return audio.astype(np.float32)

    def _demod_fm(self, iq: np.ndarray, wide: bool) -> np.ndarray:
        fs = self.sample_rate
        if wide:
            factor = max(1, int(round(fs / 240_000)))
            channel_hz = 100_000.0
            deemph_tau = 75e-6
            audio_cut = 15_000.0
        else:
            factor = max(1, int(round(fs / 48_000)))
            channel_hz = 12_500.0
            deemph_tau = None
            audio_cut = 4_000.0

        filtered, self._zi_i, self._zi_q = _decimate_complex(
            iq, factor, self._zi_i, self._zi_q, channel_hz, fs
        )
        fs_ch = fs / factor

        work = np.empty(filtered.size + 1, dtype=np.complex64)
        work[0] = self._prev
        work[1:] = filtered
        self._prev = filtered[-1]
        demod = np.angle(work[1:] * np.conj(work[:-1]))

        if deemph_tau is not None and demod.size:
            alpha = np.exp(-1.0 / (deemph_tau * fs_ch))
            out = np.empty_like(demod, dtype=np.float64)
            y = self._deemph_y
            for i, sample in enumerate(demod):
                y = y * alpha + (1.0 - alpha) * sample
                out[i] = y
            self._deemph_y = y
            demod = out

        audio = self._to_audio_rate(np.asarray(demod, dtype=np.float64), fs_ch)
        if audio.size:
            b, a = _butter_lowpass(audio_cut, self.audio_rate, order=5)
            audio, self._zi_audio = lfilter(b, a, audio, zi=self._zi_audio)
        return audio

    def _demod_am(self, iq: np.ndarray) -> np.ndarray:
        fs = self.sample_rate
        factor = max(1, int(round(fs / 48_000)))
        filtered, self._zi_i, self._zi_q = _decimate_complex(
            iq, factor, self._zi_i, self._zi_q, 8_000.0, fs
        )
        fs_ch = fs / factor
        mag = np.abs(filtered).astype(np.float64)
        mag -= np.mean(mag)
        return self._to_audio_rate(mag, fs_ch)

    def _to_audio_rate(self, audio: np.ndarray, fs_ch: float) -> np.ndarray:
        if audio.size == 0:
            return audio
        src = max(1, int(round(fs_ch)))
        dst = self.audio_rate
        if src == dst:
            return audio
        gcd = np.gcd(src, dst)
        return resample_poly(audio, dst // gcd, src // gcd)

    def _dc_block(self, audio: np.ndarray, r: float = 0.995) -> np.ndarray:
        if audio.size == 0:
            return audio
        out = np.empty_like(audio, dtype=np.float64)
        x_prev = self._dc_x
        y_prev = self._dc_y
        for i, x in enumerate(audio):
            y = x - x_prev + r * y_prev
            out[i] = y
            x_prev = x
            y_prev = y
        self._dc_x = x_prev
        self._dc_y = y_prev
        return out

    @staticmethod
    def _limit(audio: np.ndarray, ceiling: float = 0.9) -> np.ndarray:
        if audio.size == 0:
            return audio
        peak = float(np.max(np.abs(audio)))
        if peak < 1e-6:
            return np.zeros_like(audio)
        scaled = audio / peak * ceiling
        return np.clip(scaled, -1.0, 1.0)
