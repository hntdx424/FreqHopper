"""RTL-SDR device wrapper, Windows DLL discovery, and a simulation backend."""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any, Protocol

import numpy as np

WINDOWS_DRIVER_HELP = """No RTL-SDR device was found.

Windows checklist:
  1. Plug in the RTL-SDR dongle.
  2. Use Zadig (https://zadig.akeo.ie/) to install WinUSB on
     "Bulk-In, Interface (Interface 0)" — not the Composite Parent.
  3. Install librtlsdr and put these DLLs on PATH, in the FreqHopper
     folder, or in a vendor\\ folder:
       rtlsdr.dll, libusb-1.0.dll
  4. Close other programs that may be using the dongle (SDR#, GQRX, etc.).
"""

LIBRARY_HELP = """Could not load librtlsdr.

FreqHopper needs the RTL-SDR library (rtlsdr.dll on Windows).
Copy rtlsdr.dll and libusb-1.0.dll into this folder, a vendor\\ folder,
or a directory on PATH. PothosSDR's bin directory also works if it is on PATH.

Then install the WinUSB driver with Zadig if you have not already.
"""


class SdrError(RuntimeError):
    """User-visible SDR failure."""


class SdrBackend(Protocol):
    sample_rate: float
    center_freq: float

    def open(self, device_index: int) -> None: ...
    def close(self) -> None: ...
    def configure(self, sample_rate: float, gain: Any, ppm: int) -> None: ...
    def set_center_freq(self, freq_hz: float) -> None: ...
    def set_gain(self, gain: Any) -> None: ...
    def read_samples(self, n: int) -> np.ndarray: ...
    def gains_db(self) -> list[float]: ...
    def label(self) -> str: ...


def _windows_dll_dirs() -> list[Path]:
    here = Path(__file__).resolve().parent.parent
    extras = [
        Path(sys.argv[0]).resolve().parent if sys.argv else here,
        Path.cwd(),
        here,
        here / "vendor",
        Path.cwd() / "vendor",
    ]
    env_path = os.environ.get("RTLSDR_PATH")
    if env_path:
        extras.append(Path(env_path))
    program_files = Path(os.environ.get("ProgramFiles", r"C:\Program Files"))
    extras.extend(
        [
            program_files / "PothosSDR" / "bin",
            program_files / "rtl-sdr" / "bin",
            program_files / "librtlsdr" / "bin",
        ]
    )
    seen: set[Path] = set()
    ordered: list[Path] = []
    for path in extras:
        try:
            resolved = path.resolve()
        except OSError:
            continue
        if resolved not in seen:
            seen.add(resolved)
            ordered.append(resolved)
    return ordered


def prepare_native_libraries() -> Path | None:
    """Add Windows DLL directories that contain rtlsdr.dll to the load path."""
    found = None
    if sys.platform != "win32":
        return found
    for directory in _windows_dll_dirs():
        dll = directory / "rtlsdr.dll"
        if not dll.is_file():
            continue
        found = directory
        add_dir = getattr(os, "add_dll_directory", None)
        if add_dir is not None:
            try:
                add_dir(str(directory))
            except OSError:
                pass
        path = os.environ.get("PATH", "")
        prefix = str(directory)
        if prefix.lower() not in path.lower():
            os.environ["PATH"] = prefix + os.pathsep + path
        break
    return found


def _import_rtlsdr():
    prepare_native_libraries()
    try:
        from rtlsdr import RtlSdr
    except Exception as exc:
        raise SdrError(LIBRARY_HELP + f"\nDetails: {exc}") from exc
    return RtlSdr


def list_devices() -> list[str]:
    """Return labels for attached RTL-SDR devices. Empty if none."""
    RtlSdr = _import_rtlsdr()
    try:
        count = int(RtlSdr.get_device_count())
    except Exception as exc:
        raise SdrError(WINDOWS_DRIVER_HELP + f"\nDetails: {exc}") from exc
    if count <= 0:
        return []

    serials: list[str] = []
    try:
        serials = list(RtlSdr.get_device_serial_addresses())
    except Exception:
        serials = []

    labels = []
    for index in range(count):
        try:
            name = RtlSdr.get_device_name(index)
        except Exception:
            name = "RTL-SDR"
        serial = serials[index] if index < len(serials) else "?"
        labels.append(f"{index}: {name}  SN {serial}")
    return labels


class RtlSdrBackend:
    """Live pyrtlsdr wrapper."""

    def __init__(self) -> None:
        self.sample_rate = 1.2e6
        self.center_freq = 100e6
        self._sdr = None
        self._index = 0
        self._name = "RTL-SDR"

    def open(self, device_index: int) -> None:
        RtlSdr = _import_rtlsdr()
        self._index = int(device_index)
        try:
            count = int(RtlSdr.get_device_count())
        except Exception as exc:
            raise SdrError(WINDOWS_DRIVER_HELP + f"\nDetails: {exc}") from exc
        if count <= 0:
            raise SdrError(WINDOWS_DRIVER_HELP)
        if self._index < 0 or self._index >= count:
            raise SdrError(f"Device index {self._index} is out of range (found {count}).")
        try:
            self._name = RtlSdr.get_device_name(self._index)
        except Exception:
            self._name = "RTL-SDR"
        try:
            self._sdr = RtlSdr(device_index=self._index)
        except Exception as exc:
            raise SdrError(
                "Could not open the RTL-SDR. Unplug other SDR programs and confirm "
                f"the WinUSB driver is installed.\nDetails: {exc}"
            ) from exc

    def close(self) -> None:
        sdr = self._sdr
        self._sdr = None
        if sdr is None:
            return
        try:
            sdr.cancel_read_async()
        except Exception:
            pass
        try:
            sdr.close()
        except Exception:
            pass

    def configure(self, sample_rate: float, gain: Any, ppm: int) -> None:
        sdr = self._require()
        sdr.sample_rate = float(sample_rate)
        self.sample_rate = float(sdr.sample_rate)
        try:
            sdr.freq_correction = int(ppm)
        except Exception:
            pass
        self.set_gain(gain)

    def set_center_freq(self, freq_hz: float) -> None:
        sdr = self._require()
        sdr.center_freq = float(freq_hz)
        self.center_freq = float(freq_hz)

    def set_gain(self, gain: Any) -> None:
        sdr = self._require()
        if gain == "auto" or gain is None:
            sdr.gain = "auto"
            return
        sdr.gain = float(gain)

    def read_samples(self, n: int) -> np.ndarray:
        sdr = self._require()
        n = max(256, int(n))
        try:
            raw = sdr.read_bytes(n * 2)
            values = np.frombuffer(raw, dtype=np.uint8).astype(np.float32)
            values = (values - 127.4) / 128.0
            return values[0::2] + 1j * values[1::2]
        except Exception:
            samples = sdr.read_samples(n)
            return np.asarray(samples, dtype=np.complex64)

    def gains_db(self) -> list[float]:
        sdr = self._require()
        try:
            return [float(g) for g in sdr.valid_gains_db]
        except Exception:
            return []

    def label(self) -> str:
        return f"{self._index}: {self._name}"

    def _require(self):
        if self._sdr is None:
            raise SdrError("The RTL-SDR is not open.")
        return self._sdr


class FakeSdrBackend:
    """Offline IQ source used by tests and the UI simulation mode."""

    def __init__(
        self,
        noise_db: float = -55.0,
        signals: dict[float, float] | None = None,
        sample_rate: float = 1.2e6,
    ) -> None:
        self.sample_rate = sample_rate
        self.center_freq = 100e6
        self.noise_db = noise_db
        # Maps frequency Hz -> linear amplitude of an FM carrier.
        self.signals = dict(signals or {})
        self._opened = False
        self._gain: Any = "auto"

    def open(self, device_index: int) -> None:
        self._opened = True
        self._index = int(device_index)

    def close(self) -> None:
        self._opened = False

    def configure(self, sample_rate: float, gain: Any, ppm: int) -> None:
        self.sample_rate = float(sample_rate)
        self._gain = gain
        self._ppm = ppm

    def set_center_freq(self, freq_hz: float) -> None:
        self.center_freq = float(freq_hz)

    def set_gain(self, gain: Any) -> None:
        self._gain = gain

    def read_samples(self, n: int) -> np.ndarray:
        n = max(1, int(n))
        noise_power = 10 ** (self.noise_db / 10.0)
        scale = np.sqrt(noise_power / 2.0)
        iq = (
            np.random.randn(n).astype(np.float32) * scale
            + 1j * np.random.randn(n).astype(np.float32) * scale
        )
        amplitude = self._signal_amplitude(self.center_freq)
        if amplitude > 0:
            iq += _fm_test_tone(n, self.sample_rate, amplitude)
        return iq.astype(np.complex64)

    def gains_db(self) -> list[float]:
        return [0.0, 14.4, 28.0, 40.2, 49.6]

    def label(self) -> str:
        return "Simulation (no hardware)"

    def _signal_amplitude(self, freq_hz: float) -> float:
        best = 0.0
        for target, amplitude in self.signals.items():
            if abs(target - freq_hz) <= 6_000:
                best = max(best, float(amplitude))
        return best


def _fm_test_tone(n: int, fs: float, amplitude: float, tone_hz: float = 1000.0, deviation: float = 2500.0) -> np.ndarray:
    t = np.arange(n, dtype=np.float64) / fs
    message = np.sin(2.0 * np.pi * tone_hz * t)
    phase = 2.0 * np.pi * deviation * np.cumsum(message) / fs
    return (amplitude * np.exp(1j * phase)).astype(np.complex64)
