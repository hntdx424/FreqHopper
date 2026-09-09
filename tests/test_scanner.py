import time

from freqhopper.null_audio import NullAudioPlayer
from freqhopper.scanner import RuntimeParams, ScannerEngine
from freqhopper.sdr_device import FakeSdrBackend


def _wait_until(predicate, timeout=4.0, interval=0.02):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(interval)
    return False


def _engine(signals, squelch_db=-35.0, hang_s=0.05):
    freqs = [144.0e6, 146.52e6, 147.0e6]
    backend = FakeSdrBackend(noise_db=-55.0, signals=signals)
    audio = NullAudioPlayer()
    params = RuntimeParams()
    params.update(squelch_db=squelch_db, hang_s=hang_s, dwell_s=0.0, hysteresis_db=3.0)
    events: list[str] = []

    def on_status(status):
        events.append(status.state)

    engine = ScannerEngine(
        frequencies_hz=freqs,
        mode="list",
        backend=backend,
        audio=audio,
        params=params,
        scan_samples=2048,
        lock_samples=4096,
        on_status=on_status,
    )
    return engine, backend, audio, events


def test_scanner_locks_on_signal_and_plays_audio():
    engine, backend, audio, events = _engine({146.52e6: 0.5})
    engine.start()
    try:
        locked = _wait_until(lambda: "locked" in events)
        assert locked, f"never locked, states={events[-10:]}"
        assert _wait_until(lambda: audio.blocks_played > 0)
        assert audio.squelch_open
    finally:
        engine.stop()


def test_scanner_resumes_after_signal_drops():
    engine, backend, audio, events = _engine({146.52e6: 0.5}, hang_s=0.02)
    engine.start()
    try:
        assert _wait_until(lambda: "locked" in events)
        backend.signals.clear()
        resumed = _wait_until(
            lambda: events[-1] == "scanning" and not audio.squelch_open,
            timeout=5.0,
        )
        assert resumed, f"did not resume scan, last={events[-8:]}"
    finally:
        engine.stop()


def test_live_squelch_closes_lock():
    engine, backend, audio, events = _engine({146.52e6: 0.5}, hang_s=0.02)
    engine.start()
    try:
        assert _wait_until(lambda: "locked" in events)
        engine.params.update(squelch_db=0.0)
        closed = _wait_until(
            lambda: events.count("scanning") >= 2 and not audio.squelch_open,
            timeout=5.0,
        )
        assert closed, f"raising squelch did not drop lock, last={events[-8:]}"
    finally:
        engine.stop()
