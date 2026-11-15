#!/usr/bin/env python3
# Roon PeppyMeter Frame - VISUALISER EXTENSION - spectrum skin maker
#
# Copyright (C) 2026 Andrew Cox (SoftCox Developments)
# SPDX-License-Identifier: GPL-3.0-or-later
#
# This program is free software: you can redistribute it and/or modify it under the terms of
# the GNU General Public License as published by the Free Software Foundation, either
# version 3 of the License, or (at your option) any later version. See LICENSE.
"""Create the extension's own PeppySpectrum skins in vis_skins/.

Two folders are written, each with the same looks:
  1920x720-rpf-spectrum    bars in the top 720 lines, now-playing strip underneath
  1920x1080-rpf-spectrum   full screen, no strip; these start hidden ('vis unhide')
(sizes follow [display] width/height in settings.conf).

The skins use PeppySpectrum's standard spectrum.txt keys plus one of our own, rpf.bars,
the number of bars, which PeppySpectrum ignores and vis_spectrum_display.py reads.
Safe to run again: it rewrites only the two folders above.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import rpf_settings
import vis_settings

import pygame

# name, bars, colours from the bottom of a bar to the top, options
LOOKS = [
    ("Aurora 48",      48, [(0, 200, 120), (0, 170, 255), (120, 60, 255)],   {"topping": True}),
    ("Ember 32",       32, [(120, 10, 0), (255, 90, 0), (255, 220, 80)],     {"topping": True}),
    ("Ice 64",         64, [(20, 60, 160), (90, 180, 255), (235, 250, 255)], {}),
    ("Sunset 20",      20, [(90, 0, 120), (255, 60, 90), (255, 200, 60)],    {"topping": True}),
    ("Mono 96",        96, [(120, 123, 140), (255, 255, 255)],               {}),
    ("Classic LED 24", 24, [(0, 210, 60), (0, 210, 60), (0, 210, 60), (230, 220, 0), (240, 40, 20)],
                                                                           {"led": True, "topping": True}),
    ("Mirror 40",      40, [(0, 150, 140), (0, 200, 255), (200, 240, 255)],  {"mirror": True}),
]
MARGIN_X = 60
MARGIN_Y = 10      # space above and below the bars (was 60; Andrew 2026-11-14: bars 100 px taller)


def colours(cs):
    return "".join(f"({r},{g},{b})" for r, g, b in cs)


def led_bar(path, w, h, cs, seg):
    """A bar image with dark gaps between segments, for the LED look."""
    base = pygame.Surface((2, len(cs)), pygame.SRCALPHA, 32)
    for i, c in enumerate(reversed(cs)):
        pygame.draw.line(base, c, (0, i), (1, i))
    bar = pygame.transform.smoothscale(base, (w, h))
    gap = max(2, seg // 4)
    for y in range(h - seg, -seg, -seg):
        pygame.draw.rect(bar, (0, 0, 0, 255), (0, y, w, gap))
    pygame.image.save(bar, path)


def make_folder(width, height):
    folder = f"{width}x{height}-rpf-spectrum"
    path = os.path.join(vis_settings.SKINS_DIR, folder)
    os.makedirs(path, exist_ok=True)
    out = []
    for name, bars, cs, opt in LOOKS:
        pitch = (width - 2 * MARGIN_X) // bars
        gap = max(2, round(pitch * 0.2))
        bar_w = pitch - gap
        origin_x = (width - (bars * pitch - gap)) // 2
        area = height - 2 * MARGIN_Y
        mirror = opt.get("mirror", False)
        bar_h = int(area * 0.68) if mirror else area
        step = 2
        seg = opt.get("led")
        if seg:
            seg_px = max(8, bar_h // 40)          # about 40 segments
            bar_h = (bar_h // seg_px) * seg_px
            step = seg_px
        origin_y = MARGIN_Y + bar_h if mirror else height - MARGIN_Y
        lines = [f"[{name}]", f"rpf.bars = {bars}",
                 f"origin.x = {origin_x}", f"origin.y = {origin_y}", "spectrum.x = 0", "spectrum.y = 0",
                 "bgr.type = color", "bgr.color = 0,0,0", "bgr.gradient =", "bgr.filename ="]
        if seg:
            fn = f"led-{bars}.png"
            led_bar(os.path.join(path, fn), bar_w, bar_h, cs, seg_px)
            lines += ["bar.type = image", "bar.color =", "bar.gradient =", f"bar.filename = {fn}"]
        else:
            lines += ["bar.type = gradient", "bar.color =", f"bar.gradient = {colours(cs)}", "bar.filename ="]
        lines += [f"bar.width = {bar_w}", f"bar.height = {bar_h}", f"bar.gap = {gap}"]
        if mirror:
            dim = tuple(c // 3 for c in cs[0])
            lines += ["reflection.type = gradient", "reflection.color =",
                      f"reflection.gradient = {colours([(0, 0, 0), (0, 0, 0), (0, 0, 0), dim])}",
                      "reflection.filename =", "reflection.gap = 4"]
        else:
            lines += ["reflection.type =", "reflection.color =", "reflection.gradient =",
                      "reflection.filename =", "reflection.gap = 0"]
        if opt.get("topping"):
            lines += ["topping.height = 4", "topping.step = 2"]
        else:
            lines += ["topping.height =", "topping.step ="]
        lines += ["fgr.filename =", f"steps = {bar_h // step}", ""]
        out += lines
    with open(os.path.join(path, "spectrum.txt"), "w", encoding="utf-8") as f:
        f.write("\n".join(out))
    return folder


def main():
    S = rpf_settings.load()
    w, h = S.getint("display", "width"), S.getint("display", "height")
    made = [make_folder(w, h * 2 // 3), make_folder(w, h)]
    print(f"Spectrum skins written to {vis_settings.SKINS_DIR}: {', '.join(made)} ({len(LOOKS)} looks each)")
    if not os.path.exists(vis_settings.CURRENT_FILE):
        with open(vis_settings.CURRENT_FILE, "w", encoding="utf-8") as f:
            f.write(f"{made[0]}/{LOOKS[0][0]}\n")
    # First time only: the full-screen skins start hidden ('vis unhide' lists them). With
    # the strip they are the same looks as the first folder with the bars partly covered.
    if not os.path.exists(vis_settings.HIDDEN_FILE):
        with open(vis_settings.HIDDEN_FILE, "w", encoding="utf-8") as f:
            f.writelines(f"{made[1]}/{look[0]}\n" for look in LOOKS)
        print(f"The {len(LOOKS)} full-screen skins start hidden: 'vis unhide' lists them")


if __name__ == "__main__":
    main()
