#!/usr/bin/env python3
# Roon PeppyMeter Frame - VISUALISER EXTENSION - spectrum display
#
# Copyright (C) 2026 Andrew Cox (SoftCox Developments)
# SPDX-License-Identifier: GPL-3.0-or-later
#
# This program is free software: you can redistribute it and/or modify it under the terms of
# the GNU General Public License as published by the Free Software Foundation, either
# version 3 of the License, or (at your option) any later version. See LICENSE.
#
# Builds on PeppySpectrum (https://github.com/project-owner/PeppySpectrum, GPL-3.0-or-later),
# which is used unmodified: this file subclasses its Spectrum class, opens the screen at
# full size and does the drawing itself so the now-playing strip can share the screen.
"""Show a PeppySpectrum spectrum analyser, with the same Roon now-playing strip and paused
screen as the meters (both come straight from frame_display.py, which is not changed).

The skin is the one named in vis_current.txt (set by the 'vis' command). The strip sits
under skins that leave room for it; over full-screen skins it is off unless switched on
with 'vis strip dim|black|clear'.

  --snapshot FILE SECONDS   save the screen to FILE after SECONDS and exit (for testing
                            without a screen: run with SDL_VIDEODRIVER=dummy)
"""
import configparser
import os
import stat
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import rpf_settings
import vis_settings

# The strip, paused screen and screen settings are the meters' own (importing frame_display
# also makes PeppyMeter importable, which it needs; nothing of PeppyMeter is run here).
import frame_display
from frame_display import Overlay, default_strip, BLACK, SCREEN_W, SCREEN_H, MIN_FREE

import pygame
from pygame.time import Clock

V = vis_settings.load()
FPS = max(5, V.getint("display_fps"))
MODES = ("clear", "dim", "black", "off")


def die(msg):
    print(msg, flush=True)
    sys.exit(1)


def current_skin():
    """(folder, name) from vis_current.txt, or the first skin there is."""
    try:
        with open(vis_settings.CURRENT_FILE, encoding="utf-8") as f:
            folder, _, name = f.readline().strip().partition("/")
        if folder and name and (folder == "hifi" or name in sections(folder) or vis_settings.hybrid_pack(folder)):
            return folder, name
    except OSError:
        pass
    for folder in sorted(os.listdir(vis_settings.SKINS_DIR)):
        names = sections(folder)
        if names:
            return folder, names[0]
    die(f"No spectrum skins found in {vis_settings.SKINS_DIR}. Run: venv/bin/python vis_make_skins.py")


def skin_file(folder):
    c = configparser.ConfigParser(interpolation=None, strict=False)
    try:
        with open(os.path.join(vis_settings.SKINS_DIR, folder, "spectrum.txt"), encoding="utf-8", errors="replace") as f:
            c.read_string(f.read().replace("\r", ""))
    except (OSError, configparser.Error):
        pass
    return c


def sections(folder):
    return skin_file(folder).sections()


def bars_for(folder, name):
    """Number of bars: the skin's rpf.bars, else as many as fit across the skin."""
    c = skin_file(folder)
    try:
        n = int(c.get(name, "rpf.bars"))
    except (configparser.Error, ValueError):
        try:
            width = int(folder.split("x")[0])
            x, w, gap = (int(c.get(name, k)) for k in ("origin.x", "bar.width", "bar.gap"))
            n = (width - 2 * x + gap) // (w + gap)
        except (configparser.Error, ValueError, ZeroDivisionError):
            n = vis_settings.DEFAULT_BARS
    return min(max(n, 1), vis_settings.MAX_BARS)


def strip_mode(folder, name, default):
    """Per-skin strip mode from vis_strip.txt: clear, dim, black or off."""
    try:
        with open(vis_settings.STRIP_FILE, encoding="utf-8") as f:
            for line in f:
                k, _, v = line.rstrip("\n").partition("\t")
                if k == f"{folder}/{name}" and v.strip() in MODES:
                    return v.strip()
    except OSError:
        pass
    return default


def write_config(folder, name, bars, pipe, base=None):
    """PeppySpectrum reads config.txt from the current folder; give it one of our own."""
    os.makedirs(vis_settings.RUN_DIR, exist_ok=True)
    with open(os.path.join(vis_settings.RUN_DIR, "config.txt"), "w", encoding="utf-8") as f:
        f.write(f"""# Written by vis_spectrum_display.py at every start - edits are lost.
[current]
spectrum = {name}
base.folder = {base or vis_settings.SKINS_DIR}
spectrum.folder = {folder}
update.period = 1000000
max.value = 100
pipe.name = {pipe}
size = {bars}
update.ui.interval = {1.0 / FPS:.4f}
frame.rate = {FPS}
depth = 32
exit.on.touch = False
use.logging = False
use.test.data =

[sdl.env]
framebuffer.device = /dev/fb0
mouse.device =
mouse.driver =
mouse.enabled = False
video.driver = dummy
video.display =
double.buffer = True
no.frame = True
""")


def ensure_fifo(path):
    if os.path.exists(path) and not stat.S_ISFIFO(os.stat(path).st_mode):
        os.remove(path)
    if not os.path.exists(path):
        os.mkfifo(path, 0o666)


def main():
    snapshot = None
    if len(sys.argv) == 4 and sys.argv[1] == "--snapshot":
        snapshot = (sys.argv[2], float(sys.argv[3]))

    if not os.path.isfile(os.path.join(vis_settings.SPECTRUM_DIR, "spectrum.py")):
        die(f"PeppySpectrum not found in {vis_settings.SPECTRUM_DIR}. Run: bash vis_install.sh")
    folder, name = current_skin()
    if folder == "hifi":
        # Oscilloscope, goniometer, waterfall: that is vis_hifi_display.py's job
        os.execv(sys.executable, [sys.executable, os.path.join(HERE, "vis_hifi_display.py")] + sys.argv[1:])
    if vis_settings.hybrid_pack(folder):
        # A meter + spectrum skin: that is vis_hybrid_display.py's job
        os.execv(sys.executable, [sys.executable, os.path.join(HERE, "vis_hybrid_display.py")] + sys.argv[1:])
    bars = bars_for(folder, name)
    pipe = vis_settings.spectrum_pipe(bars)
    ensure_fifo(pipe)
    write_config(folder, name, bars, pipe)
    os.chdir(vis_settings.RUN_DIR)
    sys.path.insert(0, vis_settings.SPECTRUM_DIR)

    from spectrum import Spectrum
    import spectrumconfigparser as K

    class FrameSpectrum(Spectrum):
        def init_display(self):
            # The screen is the configured size; the skin keeps the size in its folder name.
            skin = self.config[K.SCREEN_WIDTH], self.config[K.SCREEN_HEIGHT]
            self.config[K.SCREEN_WIDTH], self.config[K.SCREEN_HEIGHT] = SCREEN_W, SCREEN_H
            try:
                super().init_display()
            finally:
                self.config[K.SCREEN_WIDTH], self.config[K.SCREEN_HEIGHT] = skin

        def get_backgrounds(self):
            # PeppySpectrum has no background for a blank or unknown bgr.type and then fails;
            # give those skins a black one.
            out, all_configs = [], self.spectrum_configs
            for config in all_configs:
                self.spectrum_configs = [config]
                try:
                    got = super().get_backgrounds()
                except Exception:
                    got = []
                if not got or got[0] is None:
                    got = [pygame.Surface((self.bounding_box.w, self.bounding_box.h))]
                out.append(got[0])
            self.spectrum_configs = all_configs
            return out

    sp = FrameSpectrum(None, True)
    sp.callback_start = lambda s: None        # we draw; PeppySpectrum only reads the pipe
    sp.start()
    screen = sp.util.pygame_screen
    full = screen.get_rect()
    cfg = sp.spectrum_configs[0]
    skin_rect = pygame.Rect(0, 0, sp.config[K.SCREEN_WIDTH], sp.config[K.SCREEN_HEIGHT]).clip(full)

    # Static picture: background now, kept as a copy to repaint behind the moving bars
    screen.fill(BLACK)
    sp.components[0].draw()
    backdrop = screen.copy()
    fgr = sp.components[-1]
    fgr.draw()

    # The part of the screen the bars, toppings and reflections can touch
    x0 = cfg[K.ORIGIN_X] + cfg[K.SPECTRUM_X]
    base = cfg[K.ORIGIN_Y] + cfg[K.SPECTRUM_Y]
    pitch = cfg[K.BAR_WIDTH] + cfg[K.BAR_GAP]
    top = base - cfg[K.BAR_HEIGHT] - (cfg[K.TOPPING_HEIGHT] or 0) - (cfg[K.TOPPING_STEP] or 0) - 2
    bottom = base + 2
    if cfg.get(K.REFLECTION_TYPE):
        bottom += (cfg.get(K.REFLECTION_GAP) or 0) + cfg[K.BAR_HEIGHT]
    bars_rect = pygame.Rect(x0, top, bars * pitch, bottom - top).clip(skin_rect)

    free = SCREEN_H - skin_rect.h
    strip = pygame.Rect(0, skin_rect.h, SCREEN_W, free) if free >= MIN_FREE else default_strip()
    mode = strip_mode(folder, name, "clear" if free >= MIN_FREE else "off")
    overlay = Overlay(screen, strip)
    if mode != "off":
        overlay.capture_background(mode)
    print(f"Spectrum '{folder}/{name}': {bars} bars, strip {tuple(strip)} {mode}, {FPS} fps", flush=True)
    pygame.display.update(full)

    def draw_bars():
        screen.set_clip(bars_rect)
        screen.blit(backdrop, bars_rect.topleft, bars_rect)
        for comp in sp.components[1:]:
            comp.draw()
        screen.set_clip(None)

    clock = Clock()
    paused_view = False
    frames = 0
    pygame.event.clear()
    while True:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                sp.exit()

        overlay.tick()
        if overlay.state() == "paused":
            if not paused_view or overlay.dirty:
                overlay.draw_paused()
                pygame.display.update(full)
                paused_view = True
        elif paused_view:
            screen.blit(backdrop, (0, 0))
            fgr.draw()
            draw_bars()
            overlay.dirty = True
            if mode != "off":
                overlay.draw_strip(None)
            pygame.display.update(full)
            paused_view = False
        else:
            draw_bars()
            areas = [bars_rect]
            if mode != "off":
                areas = overlay.draw_strip(areas)
            pygame.display.update(areas)

        frames += 1
        if snapshot and frames >= snapshot[1] * FPS:
            pygame.image.save(screen, snapshot[0])
            print(f"Snapshot saved to {snapshot[0]}", flush=True)
            os._exit(0)
        clock.tick(FPS)


if __name__ == "__main__":
    main()
