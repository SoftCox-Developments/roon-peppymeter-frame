# Roon PeppyMeter Frame - VISUALISER EXTENSION - shared settings and paths
#
# Copyright (C) 2026 Andrew Cox (SoftCox Developments)
# SPDX-License-Identifier: GPL-3.0-or-later
#
# This program is free software: you can redistribute it and/or modify it under the terms of
# the GNU General Public License as published by the Free Software Foundation, either
# version 3 of the License, or (at your option) any later version. See LICENSE.
"""Paths and settings for the visualiser extension (all files named vis_*).

Settings live in an optional [vis] section of the main settings.conf; every key has a
default here, so the section can be left out. Nothing in rpf_settings.py is changed.
"""
import configparser
import os

import rpf_settings

BASE_DIR = rpf_settings.BASE_DIR
SPECTRUM_DIR = os.path.join(BASE_DIR, "PeppySpectrum")   # upstream PeppySpectrum, cloned by vis_install.sh
SKINS_DIR = os.path.join(BASE_DIR, "vis_skins")           # spectrum skins (made by vis_make_skins.py)
RUN_DIR = os.path.join(BASE_DIR, "vis_run")               # generated PeppySpectrum config.txt lives here
CURRENT_FILE = os.path.join(BASE_DIR, "vis_current.txt")  # the chosen visualiser: FOLDER/NAME
STRIP_FILE = os.path.join(BASE_DIR, "vis_strip.txt")      # per-skin strip mode (vis strip)
HIDDEN_FILE = os.path.join(BASE_DIR, "vis_hidden.txt")    # hidden skins (vis hide / unhide)

# One FIFO per bar count: the display creates /tmp/rpf_spectrum_<bars> and reads it;
# the audio hub finds it by name and sends frames of that many bars. No other coordination.
SPECTRUM_PIPE_PREFIX = "/tmp/rpf_spectrum_"
DEFAULT_BARS = 20
MAX_BARS = 128

DEFAULTS = {
    "spectrum_fps": "60",        # spectrum frames sent per second (the display polls at display_fps)
    "analysis_fps": "30",        # times per second the audio is re-analysed (frames in between reuse the last result)
    "display_fps": "30",         # screen updates per second for visualisers
    "fft_size": "4096",          # samples analysed per frame (4096 at 44.1 kHz = 93 ms, 10.8 Hz resolution)
    "freq_low": "40",            # Hz, left edge of the first bar
    "freq_high": "16000",        # Hz, right edge of the last bar
    "db_floor": "-60",           # level (dB below a full-scale sine) drawn as an empty bar
    "db_top": "-12",             # level drawn as a full bar
    "tilt_db_per_octave": "3",   # lifts treble / lowers bass around 1 kHz so music fills the screen evenly
    "gain_db": "0",              # raise or lower all bars
    "attack": "0.7",             # 0-1: how fast bars rise (1 = instantly)
    "fall_time": "0.5",          # seconds for a full bar to fall to nothing
}


class VisSettings:
    def __init__(self):
        self._c = configparser.ConfigParser(interpolation=None)
        self._c.read_dict({"vis": DEFAULTS})
        self._c.read(rpf_settings.SETTINGS_FILE, encoding="utf-8")

    def getfloat(self, key):
        try:
            return float(self._c.get("vis", key).strip())
        except ValueError:
            return float(DEFAULTS[key])

    def getint(self, key):
        return int(round(self.getfloat(key)))


def load():
    return VisSettings()


def spectrum_pipe(bars):
    return f"{SPECTRUM_PIPE_PREFIX}{int(bars)}"
