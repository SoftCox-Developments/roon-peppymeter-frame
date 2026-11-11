#!/usr/bin/env python3
# Roon PeppyMeter Frame - set up PeppyMeter's config.txt (run by install.sh)
#
# Copyright (C) 2026 Andrew Cox (SoftCox Developments)
# SPDX-License-Identifier: GPL-3.0-or-later
"""Point PeppyMeter at our skins, screen, pipe and display settings.

Safe to run again: keeps the current skin if it still exists, and saves the
original config.txt once as config.txt.orig.
"""
import configparser
import os
import re
import shutil
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import rpf_settings

DEFAULT_FOLDER = "1920x1080-balbuze"
DEFAULT_METER = "blue-circ"


def skin_names(folder):
    path = os.path.join(rpf_settings.SKINS_DIR, folder, "meters.txt")
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            return re.findall(r"^\[(.*?)\][ \t\r]*$", f.read(), re.M)
    except OSError:
        return []


def main():
    S = rpf_settings.load()
    cfg_path = os.path.join(rpf_settings.PEPPY_DIR, "config.txt")
    if not os.path.isfile(cfg_path):
        sys.exit(f"Not found: {cfg_path}")
    if not os.path.exists(cfg_path + ".orig"):
        shutil.copy2(cfg_path, cfg_path + ".orig")

    c = configparser.ConfigParser(interpolation=None)
    c.optionxform = str
    c.read(cfg_path, encoding="utf-8")

    def put(section, key, value):
        if not c.has_section(section):
            c.add_section(section)
        c.set(section, key, str(value))

    folder = c.get("current", "meter.folder", fallback="")
    meter = c.get("current", "meter", fallback="")
    if meter not in skin_names(folder):
        folder, meter = DEFAULT_FOLDER, DEFAULT_METER
        if meter not in skin_names(folder):
            sys.exit(f"Default skin {folder}/{meter} not found in {rpf_settings.SKINS_DIR}")

    put("current", "meter", meter)
    put("current", "meter.folder", folder)
    put("current", "base.folder", rpf_settings.SKINS_DIR)
    put("current", "screen.width", S.getint("display", "width"))
    put("current", "screen.height", S.getint("display", "height"))
    put("current", "frame.rate", 60)
    put("current", "exit.on.touch", False)
    put("current", "stop.display.on.touch", False)
    put("current", "output.display", True)
    put("current", "use.logging", False)

    put("sdl.env", "framebuffer.device", "/dev/fb0")
    put("sdl.env", "mouse.enabled", False)
    put("sdl.env", "video.driver", "kmsdrm")
    put("sdl.env", "video.display", "")
    put("sdl.env", "double.buffer", True)
    put("sdl.env", "no.frame", True)

    put("data.source", "type", "pipe")
    put("data.source", "pipe.name", rpf_settings.PIPE)
    put("data.source", "polling.interval", 0.0167)
    put("data.source", "volume.constant", 80.0)
    put("data.source", "volume.min", 0.0)
    put("data.source", "volume.max", 100.0)
    put("data.source", "volume.max.in.pipe", 32767.0)
    put("data.source", "smooth.buffer.size", 4)

    with open(cfg_path, "w", encoding="utf-8") as f:
        c.write(f)
    print(f"PeppyMeter configured: skin {folder}/{meter}")


if __name__ == "__main__":
    main()
