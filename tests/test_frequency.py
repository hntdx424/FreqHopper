from freqhopper.frequency import (
    FrequencyError,
    format_mhz,
    parse_frequency_hz,
    parse_frequency_list,
    range_frequencies_hz,
)
import pytest


def test_parse_mhz_decimal():
    assert parse_frequency_hz("146.52") == pytest.approx(146.52e6)


def test_parse_explicit_units():
    assert parse_frequency_hz("146.52 MHz") == pytest.approx(146.52e6)
    assert parse_frequency_hz("162550 kHz") == pytest.approx(162.55e6)
    assert parse_frequency_hz("100000000 Hz") == pytest.approx(100e6)


def test_parse_integer_khz_and_mhz():
    assert parse_frequency_hz("146520") == pytest.approx(146.52e6)
    assert parse_frequency_hz("144") == pytest.approx(144e6)


def test_parse_list_keeps_units():
    freqs = parse_frequency_list("146.52 MHz, 162.55\n462.5625")
    assert freqs[0] == pytest.approx(146.52e6)
    assert freqs[1] == pytest.approx(162.55e6)
    assert freqs[2] == pytest.approx(462.5625e6)


def test_parse_list_dedupes():
    freqs = parse_frequency_list("146.52, 146.520 MHz, 147")
    assert len(freqs) == 2


def test_parse_rejects_empty():
    with pytest.raises(FrequencyError):
        parse_frequency_list("   ")


def test_range_inclusive_on_grid():
    freqs = range_frequencies_hz(144e6, 148e6, 25e3)
    assert freqs[0] == pytest.approx(144e6)
    assert freqs[-1] == pytest.approx(148e6)
    assert len(freqs) == 161


def test_range_does_not_force_offgrid_end():
    freqs = range_frequencies_hz(144e6, 148e6, 15e3)
    assert freqs[0] == pytest.approx(144e6)
    assert freqs[-1] == pytest.approx(147.990e6)
    assert freqs[-1] <= 148e6 + 1


def test_format_mhz():
    assert format_mhz(146.52e6) == "146.520 MHz"
