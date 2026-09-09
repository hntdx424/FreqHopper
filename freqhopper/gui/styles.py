STYLE_SHEET = """
QMainWindow, QWidget {
    background: #161920;
    color: #e7eaf0;
}
QGroupBox {
    border: 1px solid #2c3340;
    border-radius: 8px;
    margin-top: 14px;
    padding: 12px 10px 10px 10px;
    font-weight: 600;
    color: #c5cddb;
}
QGroupBox::title {
    subcontrol-origin: margin;
    left: 10px;
    padding: 0 6px;
}
QLineEdit, QPlainTextEdit, QComboBox, QSpinBox, QDoubleSpinBox {
    background: #0f1218;
    color: #e7eaf0;
    border: 1px solid #323a49;
    border-radius: 5px;
    padding: 4px 6px;
    selection-background-color: #3d6d8c;
}
QComboBox QAbstractItemView {
    background: #1c212c;
    color: #e7eaf0;
    selection-background-color: #2f5f7c;
}
QPushButton {
    background: #2a3140;
    color: #e7eaf0;
    border: 1px solid #3a4354;
    border-radius: 6px;
    padding: 7px 16px;
    font-weight: 600;
}
QPushButton:hover {
    background: #343c4e;
}
QPushButton:disabled {
    color: #7b8494;
    background: #222733;
}
QPushButton#startButton {
    background: #1f6a45;
    border-color: #2e8a5a;
}
QPushButton#startButton:hover {
    background: #258155;
}
QPushButton#stopButton {
    background: #7a3030;
    border-color: #9a4040;
}
QPushButton#stopButton:hover {
    background: #8d3838;
}
QSlider::groove:horizontal {
    height: 6px;
    background: #2a3140;
    border-radius: 3px;
}
QSlider::handle:horizontal {
    background: #7ec8e3;
    width: 16px;
    margin: -6px 0;
    border-radius: 8px;
}
QSlider::sub-page:horizontal {
    background: #3d8ead;
    border-radius: 3px;
}
QLabel#freqReadout {
    font-size: 28px;
    font-weight: 700;
    font-family: "Cascadia Mono", "Consolas", "Segoe UI", monospace;
    color: #7ef0a2;
}
QLabel#stateReadout {
    font-size: 13px;
    font-weight: 700;
    letter-spacing: 1px;
    color: #9aa3b5;
}
QStatusBar {
    background: #10141b;
    color: #9aa3b5;
}
QCheckBox, QRadioButton {
    spacing: 8px;
}
QRadioButton::indicator, QCheckBox::indicator {
    width: 16px;
    height: 16px;
}
"""
