"""Application entry point."""

from __future__ import annotations

import argparse
import sys

from freqhopper import __version__


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="freqhopper",
        description="RTL-SDR frequency scanner with squelch-gated audio (Windows desktop).",
    )
    parser.add_argument("--version", action="version", version=f"FreqHopper {__version__}")
    parser.add_argument(
        "--demo",
        action="store_true",
        help="Start with simulation mode enabled (no RTL-SDR required).",
    )
    args = parser.parse_args(argv)

    from PySide6.QtGui import QFont
    from PySide6.QtWidgets import QApplication

    qt_args = [sys.argv[0]]
    app = QApplication(qt_args)
    app.setApplicationName("FreqHopper")
    app.setOrganizationName("FreqHopper")
    font = QFont("Segoe UI")
    if not font.exactMatch():
        font = QFont("Noto Sans")
    font.setPointSize(10)
    app.setFont(font)

    from freqhopper.gui.main_window import MainWindow

    window = MainWindow(demo=args.demo)
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
