"""Parse and format radio frequencies from user text."""

from __future__ import annotations

import re
from collections.abc import Iterable

_UNIT_RE = re.compile(
    r"^\s*([+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?)\s*"
    r"(hz|khz|mhz|ghz)?\s*$",
    re.IGNORECASE,
)

_TOKEN_RE = re.compile(
    r"[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?\s*(?:hz|khz|mhz|ghz)?",
    re.IGNORECASE,
)


class FrequencyError(ValueError):
    """Raised when user-entered frequency text cannot be parsed."""


def parse_frequency_hz(text: str) -> float:
    """Parse a single frequency. Bare decimals are treated as MHz."""
    raw = text.strip()
    if not raw:
        raise FrequencyError("Frequency is empty.")

    match = _UNIT_RE.match(raw)
    if not match:
        raise FrequencyError(f"Could not parse frequency: {text!r}")

    value = float(match.group(1))
    unit = (match.group(2) or "").lower()

    if unit == "hz":
        hz = value
    elif unit == "khz":
        hz = value * 1e3
    elif unit == "ghz":
        hz = value * 1e9
    elif unit == "mhz":
        hz = value * 1e6
    elif "." in match.group(1) or "e" in match.group(1).lower():
        hz = value * 1e6
    elif abs(value) >= 1e6:
        hz = value
    elif abs(value) >= 1000:
        hz = value * 1e3
    else:
        hz = value * 1e6

    if hz <= 0:
        raise FrequencyError("Frequency must be positive.")
    return float(hz)


def parse_frequency_list(text: str) -> list[float]:
    """Parse comma, semicolon, newline, or space separated frequencies."""
    matches = [match.group(0) for match in _TOKEN_RE.finditer(text)]
    if not matches:
        raise FrequencyError("Enter at least one frequency.")

    freqs: list[float] = []
    seen: set[int] = set()
    for chunk in matches:
        hz = parse_frequency_hz(chunk)
        key = round(hz)
        if key in seen:
            continue
        seen.add(key)
        freqs.append(hz)
    return freqs


def range_frequencies_hz(start_hz: float, end_hz: float, step_hz: float) -> list[float]:
    """Walk [start, end] inclusive using step_hz."""
    if step_hz <= 0:
        raise FrequencyError("Step size must be greater than zero.")
    if start_hz <= 0 or end_hz <= 0:
        raise FrequencyError("Start and end frequencies must be positive.")

    lo, hi = (start_hz, end_hz) if start_hz <= end_hz else (end_hz, start_hz)
    n = int((hi - lo) / step_hz) + 1
    if n > 25_000:
        raise FrequencyError(
            f"Range would produce {n:,} channels. Increase the step size."
        )
    freqs = [float(lo + i * step_hz) for i in range(n)]
    if freqs[-1] > hi + step_hz * 0.01:
        freqs.pop()
    if not freqs:
        freqs = [float(lo)]
    return freqs


def format_mhz(hz: float, digits: int = 3) -> str:
    """Format Hz as a scanner-style MHz string."""
    mhz = hz / 1e6
    return f"{mhz:.{digits}f} MHz"


def format_hz_compact(hz: float) -> str:
    if hz >= 1e9:
        return f"{hz / 1e9:.6g} GHz"
    if hz >= 1e6:
        return f"{hz / 1e6:.6g} MHz"
    if hz >= 1e3:
        return f"{hz / 1e3:.6g} kHz"
    return f"{hz:.0f} Hz"


def mhz_list_to_text(values_mhz: Iterable[float]) -> str:
    return "\n".join(f"{value:.3f}" for value in values_mhz)
