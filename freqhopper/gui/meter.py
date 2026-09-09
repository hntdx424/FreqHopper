"""Signal vs squelch level meter."""

from __future__ import annotations

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QLinearGradient, QPainter, QPen
from PySide6.QtWidgets import QWidget

from freqhopper.defaults import METER_MAX_DB, METER_MIN_DB


class LevelMeter(QWidget):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._signal = METER_MIN_DB
        self._squelch = -35.0
        self._open = False
        self.setMinimumHeight(36)
        self.setMinimumWidth(220)

    def set_levels(self, signal_db: float, squelch_db: float, squelch_open: bool) -> None:
        self._signal = float(signal_db)
        self._squelch = float(squelch_db)
        self._open = bool(squelch_open)
        self.update()

    def _x(self, db: float, width: float) -> float:
        span = METER_MAX_DB - METER_MIN_DB
        ratio = (db - METER_MIN_DB) / span
        return max(0.0, min(1.0, ratio)) * width

    def paintEvent(self, _event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = self.rect().adjusted(1, 6, -1, -6)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor("#0f1218"))
        painter.drawRoundedRect(rect, 6, 6)

        width = float(rect.width())
        signal_w = self._x(self._signal, width)
        fill = QRectF(rect.x(), rect.y(), signal_w, rect.height())
        gradient = QLinearGradient(fill.topLeft(), fill.topRight())
        if self._open:
            gradient.setColorAt(0.0, QColor("#c9a227"))
            gradient.setColorAt(1.0, QColor("#e36b3a"))
        else:
            gradient.setColorAt(0.0, QColor("#1f6a4a"))
            gradient.setColorAt(1.0, QColor("#3ecf8e"))
        painter.setBrush(gradient)
        painter.drawRoundedRect(fill, 6, 6)

        squelch_x = rect.x() + self._x(self._squelch, width)
        painter.setPen(QPen(QColor("#f4f7ff"), 2))
        painter.drawLine(int(squelch_x), rect.y() - 3, int(squelch_x), rect.bottom() + 3)

        painter.setPen(QColor("#e7eaf0"))
        label = f"{self._signal:5.1f} dB"
        painter.drawText(rect.adjusted(8, 0, -8, 0), Qt.AlignmentFlag.AlignVCenter, label)
        painter.end()
