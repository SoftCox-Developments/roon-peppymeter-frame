# Roon PeppyMeter Frame - shared settings and paths
#
# Copyright (C) 2026 Andrew Cox (SoftCox Developments)
# SPDX-License-Identifier: GPL-3.0-or-later
#
# This program is free software: you can redistribute it and/or modify it under the terms of
# the GNU General Public License as published by the Free Software Foundation, either
# version 3 of the License, or (at your option) any later version. See LICENSE.
"""Paths and settings.conf access shared by all parts of Roon PeppyMeter Frame."""
import configparser
import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SETTINGS_FILE = os.path.join(BASE_DIR, "settings.conf")
PEPPY_DIR = os.path.join(BASE_DIR, "PeppyMeter")       # upstream PeppyMeter, cloned by install.sh
SKINS_DIR = os.path.join(BASE_DIR, "skins")             # balbuze/Meter-peppymeter, cloned by install.sh
TOKEN_FILE = os.path.join(BASE_DIR, "roon_token.json")  # Roon pairing token - keep private
STRIP_FILE = os.path.join(BASE_DIR, "meter_strip.txt")  # per-skin strip background (meter strip)

PIPE = "/tmp/rpf_peppy_pipe"                            # audio peaks -> PeppyMeter (a FIFO, no disk writes)
# RAM only, so the SD card isn't worn. Created by systemd (RuntimeDirectory= in rpf-roon.service).
# Not /dev/shm: systemd-logind empties a user's files there when that user's last login session ends.
META_DIR = "/run/roon-peppymeter-frame"
JSON_FILE = os.path.join(META_DIR, "now_playing.json")
ART_FILE = os.path.join(META_DIR, "current_art.jpg")

DEFAULTS = {
    "roon": {
        "zone": "",
        "core_ip": "",
        "core_port": "9330",
        "extension_name": "Frame Display Bridge",
    },
    "audio": {
        "device": "",
        "rate": "44100",
        "updates_per_sec": "120",
    },
    "display": {
        "width": "1920",
        "height": "1080",
        "font": "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "dim_level": "150",
    },
}


class Settings:
    def __init__(self):
        self._c = configparser.ConfigParser(interpolation=None)
        self._c.read_dict(DEFAULTS)
        self._c.read(SETTINGS_FILE, encoding="utf-8")

    def get(self, section, key):
        """Setting as a string, with surrounding whitespace and quotes removed."""
        v = self._c.get(section, key, fallback="").strip()
        if len(v) >= 2 and v[0] == v[-1] and v[0] in "\"'":
            v = v[1:-1]
        return v

    def getint(self, section, key):
        try:
            return int(self.get(section, key))
        except ValueError:
            return int(DEFAULTS[section][key])


def load():
    return Settings()
