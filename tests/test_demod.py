import numpy as np
import pytest

from freqhopper.demod import Demodulator, power_dbfs
from freqhopper.sdr_device import FakeSdrBackend, _fm_test_tone


def test_power_dbfs_unit_signal():
    samples = np.ones(2048, dtype=np.complex64)
    assert power_dbfs(samples) == pytest.approx(0.0, abs=0.05)


def test_power_dbfs_silence():
    samples = np.zeros(2048, dtype=np.complex64)
    assert power_dbfs(samples) <= -100.0


def test_fake_sdr_signal_is_above_noise():
    backend = FakeSdrBackend(noise_db=-55.0, signals={146.52e6: 0.5})
    backend.open(0)
    backend.configure(1.2e6, "auto", 0)
    backend.set_center_freq(100e6)
    noise = power_dbfs(backend.read_samples(8192))
    backend.set_center_freq(146.52e6)
    signal = power_dbfs(backend.read_samples(8192))
    assert signal > noise + 15


def test_nbfm_demod_produces_audio():
    fs = 1.2e6
    iq = _fm_test_tone(65_536, fs, amplitude=0.4)
    demod = Demodulator(fs, mode="nbfm")
    audio = demod.process(iq)
    assert audio.size > 100
    assert np.max(np.abs(audio)) > 0.1
    # A 1 kHz tone should dominate after FM demod.
    spec = np.abs(np.fft.rfft(audio * np.hanning(audio.size)))
    freqs = np.fft.rfftfreq(audio.size, 1 / 48_000)
    peak = freqs[int(np.argmax(spec[1:]) + 1)]
    assert 600 < peak < 1600


def test_am_demod_produces_audio():
    fs = 1.2e6
    t = np.arange(32_768) / fs
    carrier = np.exp(1j * 2 * np.pi * 1000 * t)
    iq = ((1.0 + 0.5 * np.sin(2 * np.pi * 800 * t)) * carrier).astype(np.complex64)
    audio = Demodulator(fs, mode="am").process(iq)
    assert audio.size > 100
    assert np.max(np.abs(audio)) > 0.05
