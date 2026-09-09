"""Null audio sink for tests and hosts without PortAudio."""

from __future__ import annotations

import numpy as np


class NullAudioPlayer:
    def __init__(self) -> None:
        self.available = True
        self.error_message = ""
        self.volume = 1.0
        self.blocks_played = 0
        self.samples_played = 0
        self._open = False

    def start(self) -> None:
        return

    def stop(self) -> None:
        self.mute()

    def unmute(self) -> None:
        self._open = True

    def mute(self) -> None:
        self._open = False

    @property
    def squelch_open(self) -> bool:
        return self._open

    def play(self, samples: np.ndarray) -> None:
        if not self._open:
            return
        self.blocks_played += 1
        self.samples_played += int(np.asarray(samples).size)
