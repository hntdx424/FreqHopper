"""FreqHopper main window."""

from __future__ import annotations

from PySide6.QtCore import Qt, QObject, Signal, Slot
from PySide6.QtWidgets import (
    QButtonGroup,
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFormLayout,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QRadioButton,
    QSlider,
    QSpinBox,
    QStackedWidget,
    QStatusBar,
    QVBoxLayout,
    QWidget,
)

from freqhopper.defaults import (
    DEFAULT_END_MHZ,
    DEFAULT_GAIN,
    DEFAULT_LIST_MHZ,
    DEFAULT_PPM,
    DEFAULT_SQUELCH_DB,
    DEFAULT_START_MHZ,
    DEFAULT_STEP_KHZ,
    DEFAULT_VOLUME,
    SQUELCH_MAX_DB,
    SQUELCH_MIN_DB,
)
from freqhopper.demod import modulation_choices
from freqhopper.frequency import (
    FrequencyError,
    format_mhz,
    mhz_list_to_text,
    parse_frequency_hz,
    parse_frequency_list,
    range_frequencies_hz,
)
from freqhopper.gui.meter import LevelMeter
from freqhopper.gui.styles import STYLE_SHEET
from freqhopper.scanner import RuntimeParams, ScannerEngine, ScanStatus
from freqhopper.sdr_device import FakeSdrBackend, SdrError, list_devices

PRESETS = {
    "2 m amateur (US)": {
        "mode": "range",
        "start": 144.0,
        "end": 148.0,
        "step_khz": 15.0,
    },
    "70 cm amateur (US)": {
        "mode": "range",
        "start": 440.0,
        "end": 450.0,
        "step_khz": 25.0,
    },
    "NOAA weather": {
        "mode": "range",
        "start": 162.400,
        "end": 162.550,
        "step_khz": 25.0,
    },
    "2 m calling + NOAA": {
        "mode": "list",
        "freqs": DEFAULT_LIST_MHZ,
    },
}


class _Bridge(QObject):
    status = Signal(object)
    error = Signal(str)


class MainWindow(QMainWindow):
    def __init__(self, demo: bool = False) -> None:
        super().__init__()
        self.setWindowTitle("FreqHopper")
        self.setMinimumSize(760, 780)
        self.resize(800, 840)
        self.setStyleSheet(STYLE_SHEET)

        self.params = RuntimeParams()
        self.engine: ScannerEngine | None = None
        self.bridge = _Bridge()
        self.bridge.status.connect(self._on_status)
        self.bridge.error.connect(self._on_error)

        self._build()
        self._refresh_devices()
        if demo:
            self.simulate_box.setChecked(True)
        self._apply_preset("2 m amateur (US)")
        self._set_running_ui(False)
        self._update_squelch_label()
        self.statusBar().showMessage("Idle — connect an RTL-SDR or enable simulation.")

    def _build(self) -> None:
        root = QWidget()
        layout = QVBoxLayout(root)
        layout.setContentsMargins(14, 14, 14, 10)
        layout.setSpacing(10)

        layout.addWidget(self._build_readout())
        layout.addWidget(self._build_squelch())
        layout.addWidget(self._build_mode())
        layout.addWidget(self._build_device())
        layout.addWidget(self._build_controls())
        layout.addStretch(1)

        self.setCentralWidget(root)
        status = QStatusBar()
        self.setStatusBar(status)

    def _build_readout(self) -> QWidget:
        box = QGroupBox("Status")
        grid = QGridLayout(box)
        self.freq_label = QLabel(format_mhz(DEFAULT_START_MHZ * 1e6))
        self.freq_label.setObjectName("freqReadout")
        self.state_label = QLabel("IDLE")
        self.state_label.setObjectName("stateReadout")
        self.mode_value = QLabel("Range")
        self.squelch_state = QLabel("CLOSED")
        self.device_value = QLabel("No device")
        self.channel_value = QLabel("—")
        self.signal_value = QLabel("— dB")

        self.meter = LevelMeter()
        self.meter.set_levels(-80.0, DEFAULT_SQUELCH_DB, False)

        grid.addWidget(self.freq_label, 0, 0, 1, 2)
        grid.addWidget(self.state_label, 0, 2, 1, 2, Qt.AlignmentFlag.AlignRight)
        grid.addWidget(QLabel("Mode"), 1, 0)
        grid.addWidget(self.mode_value, 1, 1)
        grid.addWidget(QLabel("Squelch"), 2, 0)
        grid.addWidget(self.squelch_state, 2, 1)
        grid.addWidget(QLabel("Device"), 3, 0)
        grid.addWidget(self.device_value, 3, 1, 1, 2)
        grid.addWidget(QLabel("Channel"), 4, 0)
        grid.addWidget(self.channel_value, 4, 1)
        grid.addWidget(QLabel("Signal"), 4, 2)
        grid.addWidget(self.signal_value, 4, 3)
        grid.addWidget(self.meter, 5, 0, 1, 4)
        hint = QLabel("Meter: colored bar is signal level; white line is the squelch threshold.")
        hint.setStyleSheet("color:#8b93a5; font-weight:400;")
        grid.addWidget(hint, 6, 0, 1, 4)
        return box

    def _build_squelch(self) -> QWidget:
        box = QGroupBox("Squelch")
        layout = QVBoxLayout(box)
        row = QHBoxLayout()
        self.squelch_slider = QSlider(Qt.Orientation.Horizontal)
        self.squelch_slider.setRange(int(SQUELCH_MIN_DB), int(SQUELCH_MAX_DB))
        self.squelch_slider.setValue(int(DEFAULT_SQUELCH_DB))
        self.squelch_slider.valueChanged.connect(self._on_squelch_changed)
        self.squelch_label = QLabel()
        row.addWidget(self.squelch_slider, 1)
        row.addWidget(self.squelch_label)
        layout.addLayout(row)
        help_row = QLabel("Lower (left) is more sensitive. Raise the slider to require a stronger signal.")
        help_row.setStyleSheet("color:#8b93a5; font-weight:400;")
        help_row.setWordWrap(True)
        layout.addWidget(help_row)
        return box

    def _build_mode(self) -> QWidget:
        box = QGroupBox("Scan mode")
        layout = QVBoxLayout(box)

        preset_row = QHBoxLayout()
        preset_row.addWidget(QLabel("Preset"))
        self.preset_combo = QComboBox()
        self.preset_combo.addItem("Custom")
        for name in PRESETS:
            self.preset_combo.addItem(name)
        self.preset_combo.currentTextChanged.connect(self._on_preset)
        preset_row.addWidget(self.preset_combo, 1)
        layout.addLayout(preset_row)

        mode_row = QHBoxLayout()
        self.range_radio = QRadioButton("Range")
        self.list_radio = QRadioButton("List")
        self.range_radio.setChecked(True)
        self.mode_group = QButtonGroup(self)
        self.mode_group.addButton(self.range_radio)
        self.mode_group.addButton(self.list_radio)
        self.range_radio.toggled.connect(self._on_mode_toggled)
        mode_row.addWidget(self.range_radio)
        mode_row.addWidget(self.list_radio)
        mode_row.addStretch(1)
        layout.addLayout(mode_row)

        self.pages = QStackedWidget()
        self.pages.addWidget(self._build_range_page())
        self.pages.addWidget(self._build_list_page())
        layout.addWidget(self.pages)
        return box

    def _build_range_page(self) -> QWidget:
        page = QWidget()
        form = QFormLayout(page)
        form.setContentsMargins(0, 0, 0, 0)
        self.start_mhz = QDoubleSpinBox()
        self.end_mhz = QDoubleSpinBox()
        self.step_khz = QDoubleSpinBox()
        for spin, value, maximum in (
            (self.start_mhz, DEFAULT_START_MHZ, 2000.0),
            (self.end_mhz, DEFAULT_END_MHZ, 2000.0),
        ):
            spin.setDecimals(4)
            spin.setRange(0.001, maximum)
            spin.setSingleStep(0.025)
            spin.setSuffix(" MHz")
            spin.setValue(value)
        self.step_khz.setDecimals(2)
        self.step_khz.setRange(0.01, 1_000_000.0)
        self.step_khz.setSuffix(" kHz")
        self.step_khz.setValue(DEFAULT_STEP_KHZ)
        form.addRow("Start", self.start_mhz)
        form.addRow("End", self.end_mhz)
        form.addRow("Step", self.step_khz)
        return page

    def _build_list_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(QLabel("Frequencies (MHz, one per line or comma-separated)"))
        self.list_edit = QPlainTextEdit()
        self.list_edit.setPlainText(mhz_list_to_text(DEFAULT_LIST_MHZ))
        self.list_edit.setPlaceholderText("146.520\n162.550\n462.5625 MHz")
        self.list_edit.setMinimumHeight(110)
        layout.addWidget(self.list_edit)
        add_row = QHBoxLayout()
        self.add_freq = QLineEdit()
        self.add_freq.setPlaceholderText("Add one frequency, e.g. 146.52")
        add_btn = QPushButton("Add")
        add_btn.clicked.connect(self._add_list_frequency)
        add_row.addWidget(self.add_freq, 1)
        add_row.addWidget(add_btn)
        layout.addLayout(add_row)
        return page

    def _build_device(self) -> QWidget:
        box = QGroupBox("Device & receiver")
        form = QFormLayout(box)
        device_row = QHBoxLayout()
        self.device_combo = QComboBox()
        refresh = QPushButton("Refresh")
        refresh.clicked.connect(self._refresh_devices)
        device_row.addWidget(self.device_combo, 1)
        device_row.addWidget(refresh)
        form.addRow("RTL-SDR", device_row)

        self.simulate_box = QCheckBox("Simulation (no RTL-SDR hardware)")
        self.simulate_box.toggled.connect(self._on_simulate_toggled)
        form.addRow("", self.simulate_box)

        self.gain_combo = QComboBox()
        self.gain_combo.addItem("Auto", "auto")
        for gain in (14.4, 28.0, 40.2, 49.6):
            self.gain_combo.addItem(f"{gain} dB", gain)
        self.gain_combo.currentIndexChanged.connect(self._push_runtime)
        form.addRow("Gain", self.gain_combo)

        self.mod_combo = QComboBox()
        for key, label in modulation_choices():
            self.mod_combo.addItem(label, key)
        self.mod_combo.currentIndexChanged.connect(self._push_runtime)
        form.addRow("Modulation", self.mod_combo)

        self.volume_slider = QSlider(Qt.Orientation.Horizontal)
        self.volume_slider.setRange(0, 150)
        self.volume_slider.setValue(int(DEFAULT_VOLUME * 100))
        self.volume_slider.valueChanged.connect(self._push_runtime)
        form.addRow("Volume", self.volume_slider)

        dwell_hang = QHBoxLayout()
        self.dwell_ms = QSpinBox()
        self.dwell_ms.setRange(0, 2000)
        self.dwell_ms.setSuffix(" ms")
        self.dwell_ms.setValue(80)
        self.dwell_ms.valueChanged.connect(self._push_runtime)
        self.hang_ms = QSpinBox()
        self.hang_ms.setRange(0, 5000)
        self.hang_ms.setSuffix(" ms")
        self.hang_ms.setValue(750)
        self.hang_ms.valueChanged.connect(self._push_runtime)
        dwell_hang.addWidget(QLabel("Dwell"))
        dwell_hang.addWidget(self.dwell_ms)
        dwell_hang.addWidget(QLabel("Hang"))
        dwell_hang.addWidget(self.hang_ms)
        form.addRow("Timing", dwell_hang)

        self.ppm_spin = QSpinBox()
        self.ppm_spin.setRange(-150, 150)
        self.ppm_spin.setSuffix(" ppm")
        self.ppm_spin.setValue(DEFAULT_PPM)
        form.addRow("Freq. correction", self.ppm_spin)
        return box

    def _build_controls(self) -> QWidget:
        row = QWidget()
        layout = QHBoxLayout(row)
        layout.setContentsMargins(0, 0, 0, 0)
        self.start_btn = QPushButton("Start scan")
        self.start_btn.setObjectName("startButton")
        self.start_btn.clicked.connect(self._start)
        self.stop_btn = QPushButton("Stop")
        self.stop_btn.setObjectName("stopButton")
        self.stop_btn.clicked.connect(self._stop)
        layout.addWidget(self.start_btn)
        layout.addWidget(self.stop_btn)
        layout.addStretch(1)
        return row

    def _on_mode_toggled(self, _checked: bool = False) -> None:
        self.pages.setCurrentIndex(0 if self.range_radio.isChecked() else 1)
        self.mode_value.setText("Range" if self.range_radio.isChecked() else "List")

    def _on_preset(self, name: str) -> None:
        if name == "Custom":
            return
        self._apply_preset(name)

    def _apply_preset(self, name: str) -> None:
        preset = PRESETS.get(name)
        if not preset:
            return
        self.preset_combo.blockSignals(True)
        self.preset_combo.setCurrentText(name)
        self.preset_combo.blockSignals(False)
        if preset["mode"] == "range":
            self.range_radio.setChecked(True)
            self.start_mhz.setValue(preset["start"])
            self.end_mhz.setValue(preset["end"])
            self.step_khz.setValue(preset["step_khz"])
        else:
            self.list_radio.setChecked(True)
            self.list_edit.setPlainText(mhz_list_to_text(preset["freqs"]))
        self._on_mode_toggled()

    def _add_list_frequency(self) -> None:
        text = self.add_freq.text().strip()
        if not text:
            return
        try:
            hz = parse_frequency_hz(text)
        except FrequencyError as exc:
            QMessageBox.warning(self, "Invalid frequency", str(exc))
            return
        current = self.list_edit.toPlainText().strip()
        line = f"{hz / 1e6:.4f}".rstrip("0").rstrip(".")
        self.list_edit.setPlainText(f"{current}\n{line}" if current else line)
        self.add_freq.clear()
        self.preset_combo.setCurrentText("Custom")

    def _refresh_devices(self) -> None:
        self.device_combo.clear()
        if self.simulate_box.isChecked():
            self.device_combo.addItem("Simulation", 0)
            self.device_value.setText("Simulation (no hardware)")
            return
        try:
            devices = list_devices()
        except SdrError as exc:
            self.device_combo.addItem("No device / driver error", -1)
            self.device_value.setText("Driver or library error")
            self.statusBar().showMessage(str(exc).splitlines()[0])
            return
        if not devices:
            self.device_combo.addItem("No RTL-SDR found", -1)
            self.device_value.setText("No RTL-SDR found")
            self.statusBar().showMessage("No RTL-SDR found. Install WinUSB with Zadig, or enable simulation.")
            return
        for index, label in enumerate(devices):
            self.device_combo.addItem(label, index)
        self.device_value.setText(devices[0])
        self.statusBar().showMessage(f"Found {len(devices)} RTL-SDR device(s).")

    def _on_simulate_toggled(self, _checked: bool) -> None:
        self._refresh_devices()

    def _on_squelch_changed(self, value: int) -> None:
        self.params.update(squelch_db=float(value))
        self._update_squelch_label()
        self.meter.set_levels(
            getattr(self, "_last_signal", -80.0),
            float(value),
            getattr(self, "_last_open", False),
        )

    def _update_squelch_label(self) -> None:
        self.squelch_label.setText(f"{self.squelch_slider.value()} dB")

    def _push_runtime(self, *_args) -> None:
        gain = self.gain_combo.currentData()
        if gain is None:
            gain = DEFAULT_GAIN
        self.params.update(
            squelch_db=float(self.squelch_slider.value()),
            volume=self.volume_slider.value() / 100.0,
            hang_s=self.hang_ms.value() / 1000.0,
            dwell_s=self.dwell_ms.value() / 1000.0,
            modulation=self.mod_combo.currentData() or "nbfm",
            gain=gain,
            ppm=self.ppm_spin.value(),
        )

    def _collect_frequencies(self) -> tuple[list[float], str]:
        if self.range_radio.isChecked():
            start = parse_frequency_hz(f"{self.start_mhz.value()} MHz")
            end = parse_frequency_hz(f"{self.end_mhz.value()} MHz")
            step = parse_frequency_hz(f"{self.step_khz.value()} kHz")
            return range_frequencies_hz(start, end, step), "range"
        return parse_frequency_list(self.list_edit.toPlainText()), "list"

    def _start(self) -> None:
        if self.engine and self.engine.running:
            return
        try:
            frequencies, mode = self._collect_frequencies()
        except FrequencyError as exc:
            QMessageBox.warning(self, "Invalid frequencies", str(exc))
            return

        simulate = self.simulate_box.isChecked()
        device_index = int(self.device_combo.currentData() or 0)
        if not simulate and device_index < 0:
            QMessageBox.critical(
                self,
                "No RTL-SDR",
                "No RTL-SDR device is selected.\n\n"
                "Plug in a dongle, install the WinUSB driver with Zadig, "
                "put rtlsdr.dll on PATH, then click Refresh.\n\n"
                "To try the UI without hardware, enable Simulation.",
            )
            return

        self._push_runtime()
        backend = None
        audio = None
        if simulate:
            mid = frequencies[min(1, len(frequencies) - 1)]
            backend = FakeSdrBackend(signals={mid: 0.45})
            self.device_value.setText(backend.label())

        try:
            self.engine = ScannerEngine(
                frequencies_hz=frequencies,
                mode=mode,
                device_index=0 if simulate else device_index,
                backend=backend,
                audio=audio,
                params=self.params,
                on_status=self.bridge.status.emit,
                on_error=self.bridge.error.emit,
            )
            self.engine.start()
        except SdrError as exc:
            QMessageBox.critical(self, "Scanner error", str(exc))
            self.engine = None
            return

        self._set_running_ui(True)
        self.statusBar().showMessage(f"Scanning {len(frequencies)} channel(s)…")

    def _stop(self) -> None:
        engine = self.engine
        self.engine = None
        if engine is not None:
            engine.stop()
        self._set_running_ui(False)
        self.state_label.setText("STOPPED")
        self.squelch_state.setText("CLOSED")
        self.squelch_state.setStyleSheet("color:#9aa3b5;")
        self.statusBar().showMessage("Stopped")

    def _set_running_ui(self, running: bool) -> None:
        self.start_btn.setEnabled(not running)
        self.stop_btn.setEnabled(running)
        self.range_radio.setEnabled(not running)
        self.list_radio.setEnabled(not running)
        self.pages.setEnabled(not running)
        self.preset_combo.setEnabled(not running)
        self.device_combo.setEnabled(not running)
        self.simulate_box.setEnabled(not running)
        self.ppm_spin.setEnabled(not running)

    @Slot(object)
    def _on_status(self, status: ScanStatus) -> None:
        self._last_signal = status.signal_db
        self._last_open = status.squelch_open
        self.freq_label.setText(format_mhz(status.frequency_hz) if status.frequency_hz else "—")
        self.state_label.setText(status.state.upper())
        color = "#7ef0a2" if status.state == "locked" else "#9aa3b5"
        if status.state == "error":
            color = "#e36b3a"
        self.state_label.setStyleSheet(f"color:{color};")
        self.mode_value.setText("Range" if status.mode == "range" else "List")
        self.squelch_state.setText("OPEN" if status.squelch_open else "CLOSED")
        self.squelch_state.setStyleSheet("color:#e3c15a;" if status.squelch_open else "color:#9aa3b5;")
        self.device_value.setText(status.device_label)
        if status.channel_count:
            self.channel_value.setText(f"{status.index + 1} / {status.channel_count}")
        self.signal_value.setText(f"{status.signal_db:5.1f} dB")
        self.meter.set_levels(status.signal_db, status.squelch_db, status.squelch_open)
        self.statusBar().showMessage(status.message)
        if status.state in {"stopped", "error"}:
            self._set_running_ui(False)

    @Slot(str)
    def _on_error(self, message: str) -> None:
        QMessageBox.critical(self, "FreqHopper", message)
        self._set_running_ui(False)

    def closeEvent(self, event) -> None:  # noqa: N802
        self._stop()
        event.accept()
