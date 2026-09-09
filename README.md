# FreqHopper

FreqHopper is a Windows desktop **RTL-SDR scanner**. It walks a frequency range or a list of channels, measures signal strength on each one, and **opens squelch to play demodulated audio** when a signal rises above the threshold you set. When the signal drops, squelch closes (audio mutes) and scanning continues.

It is meant to feel like a conventional radio scanner: dwell on a channel, break squelch, hang for a moment after the signal fades, then move on.

## What it does

- **Range mode** — start frequency, end frequency, and step size. The scanner walks that grid forever until you press Stop.
- **List mode** — paste or type discrete frequencies (comma, semicolon, or newline separated) and cycle through them.
- **Squelch** — a live slider in dB. Raise it to ignore noise; lower it to hear weaker signals. You can move it while a scan is running.
- **Lock + hang** — a detection opens squelch and holds that frequency. A short hang time / hysteresis keeps the audio from chattering when the signal flickers.
- **Status** — current frequency, scan vs locked, signal level vs squelch (bar + marker), device state.

Primary demodulation is **NBFM** (narrow FM). WBFM and AM are included. See [Extending demodulation](#extending-demodulation) to add more modes.

## Windows prerequisites

Target: **Windows 10 / 11**, 64-bit.

### 1. RTL-SDR dongle

Any RTL2832U-based receiver (RTL-SDR Blog, NooElec NESDR, generic DVB-T sticks, etc.).

### 2. Zadig / WinUSB driver

Windows will not expose the stick to user-space SDR tools until the stock DVB-T driver is replaced.

1. Download [Zadig](https://zadig.akeo.ie/).
2. Plug in the dongle.
3. In Zadig, open **Options → List All Devices**.
4. Select **Bulk-In, Interface (Interface 0)** (it may also show as RTL2832U).
5. Choose **WinUSB** and click **Replace Driver**.

Do **not** install WinUSB on the **Composite Parent** device.

If Zadig is skipped, FreqHopper will report that no RTL-SDR was found even though Device Manager shows a TV tuner.

### 3. librtlsdr DLLs

Python’s `pyrtlsdr` bindings need the native library on Windows:

- `rtlsdr.dll`
- `libusb-1.0.dll`
- `pthreadVC2.dll` (only if your build includes it)

Copy those files into **one** of:

- the FreqHopper project folder, or
- a `vendor\` folder next to the project (see `vendor/README.txt`), or
- any directory on your `PATH`

You can also set `RTLSDR_PATH` to a folder that contains `rtlsdr.dll`.

Prebuilt Windows binaries are commonly published with [librtlsdr releases](https://github.com/librtlsdr/librtlsdr/releases) and RTL-SDR Blog / osmocom packages. Installing [PothosSDR](https://github.com/pothosware/PothosSDR/wiki) and adding its `bin` directory to `PATH` is another working option.

### 4. Python

Install **Python 3.10+** from [python.org](https://www.python.org/downloads/windows/). During setup, enable **Add python.exe to PATH**.

A sound output device is optional. If none is present, scanning and squelch still work; playback stays muted and the status line explains why.

## Install

In a Command Prompt or PowerShell session, from the project folder:

```bat
python -m venv .venv
.venv\Scripts\activate
python -m pip install --upgrade pip
pip install -r requirements.txt
```

## Run

```bat
python -m freqhopper
```

or double-click `run_freqhopper.bat`.

The first launch uses a **2 m amateur (US)** range preset (144–148 MHz, 15 kHz steps) and a squelch of **-35 dB**, which is a reasonable starting point for an RTL-SDR in auto gain.

To exercise the UI without a dongle:

```bat
python -m freqhopper --demo
```

That enables **Simulation (no RTL-SDR hardware)**. A synthetic FM signal is injected on the second channel so you can see lock / squelch / resume behavior.

## Using the scanner

### Range vs list

1. Choose **Range** or **List** at the top of Scan mode (or pick a preset).
2. **Range:** set Start (MHz), End (MHz), and Step (kHz). Example: `162.400` to `162.550` step `25` kHz for US NOAA weather.
3. **List:** enter frequencies as MHz values, one per line or comma-separated. Units are accepted (`146.52`, `146.52 MHz`, `162550 kHz`). Use **Add** to append a single channel.
4. Click **Start scan**. **Stop** releases the dongle.

While running, mode and frequency fields are locked so the channel list cannot change mid-pass. Squelch, volume, gain, modulation, dwell, and hang stay live.

### Squelch slider

- The slider is the **threshold in dBFS** of measured IQ power.
- **Left / lower dB** = more sensitive (breaks squelch on weaker signals).
- **Right / higher dB** = tighter (needs a stronger signal).
- The meter bar is the current signal. The **white line** is the squelch threshold. When the bar crosses the line, squelch opens and the state reads **LOCKED / OPEN**.
- Move the slider during a lock: if you raise it above the signal (minus a few dB of hysteresis), squelch closes after hang time and scanning resumes.

Default hysteresis is 4 dB; default hang is 750 ms. Increase hang if the audio chops at the end of transmissions.

### Gain and modulation

Auto gain is convenient but can make the noise floor wander, so the same squelch setting may feel inconsistent. For scanning, a **fixed gain** (often 20–40 dB) is usually more stable.

| Mode | Typical use |
| --- | --- |
| NBFM | Amateur, public-safety analog, FRS/GMRS, NOAA |
| WBFM | Broadcast FM (needs a stronger, wider signal) |
| AM | Airband / other AM voice |

Dwell is how long each channel is measured during a search. Shorter dwell scans faster and can miss brief transmissions; 50–120 ms is a practical range.

### Multiple dongles

If more than one RTL-SDR is plugged in, pick the index in the device dropdown and click Refresh if you hot-plug.

## Project layout

```
freqhopper/
  app.py              GUI entry
  scanner.py          Scan / lock / hang loop
  sdr_device.py       RTL-SDR + Windows DLL discovery + simulation
  demod.py            Power measurement, NBFM / WBFM / AM
  audio_player.py     Squelch-gated 48 kHz playback
  frequency.py        Frequency parsing
  gui/                PySide6 window, meter, theme
vendor/               Drop rtlsdr.dll here on Windows
tests/                Hardware-free unit tests
```

IQ sample rate defaults to **1.2 MS/s**. Audio is resampled to **48 kHz** and is written to the sound device only while squelch is open.

## Extending demodulation

1. Add a mode key in `freqhopper/demod.py` (`MODULATION_MODES` and `_MODE_LABELS`).
2. Implement the IQ → audio path in `Demodulator.process` (keep it stateful across USB blocks).
3. The modulation combo in the GUI is filled from `modulation_choices()` — no extra UI wiring.

NBFM uses a ~12.5 kHz channel filter, quadrature discriminator, and ~4 kHz audio low-pass. WBFM uses a wider channel filter and 75 µs de-emphasis. AM is envelope detection after a narrow channel filter.

## Tests

```bat
pip install -r requirements-dev.txt
python -m pytest -q
```

Tests use a simulated RTL-SDR. They do not require a dongle or audio device.

## Troubleshooting

| Symptom | What to try |
| --- | --- |
| “No RTL-SDR device was found” | Zadig WinUSB on Bulk-In Interface 0; close SDR#, HDSDR, dump1090; try another USB port. |
| “Could not load librtlsdr” | Put `rtlsdr.dll` and `libusb-1.0.dll` in the project folder or `vendor\`. |
| Scan runs but no audio | Check Windows playback device / volume mixer. Status will mention a missing audio device. Detection still works. |
| Constant open squelch | Raise the squelch slider, or switch from Auto gain to a fixed gain. |
| Never opens squelch | Lower the slider, increase gain, confirm you are on an active band, wait for a transmission. |
| Off-frequency / distorted | Set **Freq. correction** (ppm) for your dongle; cheap sticks are often 30–70 ppm. |
| Choppy audio | Increase hang time; close other USB-heavy apps; try a powered hub. |

## License

Use and modify this project as you like in the FreqHopper repository.
