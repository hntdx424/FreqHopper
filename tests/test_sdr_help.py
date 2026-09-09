from freqhopper.sdr_device import LIBRARY_HELP, WINDOWS_DRIVER_HELP


def test_driver_help_mentions_zadig():
    assert "Zadig" in WINDOWS_DRIVER_HELP
    assert "WinUSB" in WINDOWS_DRIVER_HELP
    assert "Bulk-In" in WINDOWS_DRIVER_HELP


def test_library_help_mentions_dlls():
    assert "rtlsdr.dll" in LIBRARY_HELP
    assert "libusb-1.0.dll" in LIBRARY_HELP
