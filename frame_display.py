#!/usr/bin/env python3
# Roon PeppyMeter Frame - display (PeppyMeter plus a now-playing overlay)
#
# Copyright (C) 2026 Andrew Cox (SoftCox Developments)
# SPDX-License-Identifier: GPL-3.0-or-later
#
# This program is free software: you can redistribute it and/or modify it under the terms of
# the GNU General Public License as published by the Free Software Foundation, either
# version 3 of the License, or (at your option) any later version. See LICENSE.
#
# Builds on PeppyMeter (https://github.com/project-owner/PeppyMeter, GPL-3.0-or-later),
# which is used unmodified: this file subclasses its Peppymeter class and replaces only
# the display loop.
"""Run PeppyMeter with a Roon now-playing overlay.

  - Draws title, artist, album, progress and art in a strip below the meters.
    The strip fills the space under shorter skins (e.g. 1920x720) and scales up;
    under full-screen skins it sits along the bottom. Its background can be set
    per skin to clear, dim or black (see 'meter strip').
  - Swaps the meters for large album art while Roon is paused.
Reads now_playing.json written by roon_bridge.py.
"""
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import rpf_settings

S = rpf_settings.load()
os.chdir(rpf_settings.PEPPY_DIR)
sys.path.insert(0, rpf_settings.PEPPY_DIR)

import pygame
from pygame.time import Clock
from peppymeter import Peppymeter
from configfileparser import (SCREEN_RECT, FRAME_RATE, DATA_SOURCE, TYPE, METER, SCREEN_INFO,
                              METER_FOLDER, BASE_PATH, BGR_FILENAME, METER_Y, WIDTH, HEIGHT)
from datasource import SOURCE_PIPE

JSON_FILE = rpf_settings.JSON_FILE
ART_FILE = rpf_settings.ART_FILE
STRIP_FILE = rpf_settings.STRIP_FILE
FONT = S.get("display", "font")
DIM_LEVEL = max(0, min(255, S.getint("display", "dim_level")))
SCREEN_W = S.getint("display", "width")
SCREEN_H = S.getint("display", "height")

STRIP_H = 250                     # default strip: along the bottom of full-screen skins
MIN_FREE = 300                    # use the space under a shorter skin if at least this tall
MARGIN = 60
BIG_ART = 760
SIZES = {"title": 56, "artist": 40, "album": 34, "time": 30}
WHITE, GREY, DIM, TRACK = (255, 255, 255), (200, 203, 216), (154, 157, 179), (74, 77, 106)
BLACK = (0, 0, 0)
POLL = 0.25


def default_strip():
    return pygame.Rect(0, SCREEN_H - STRIP_H, SCREEN_W, STRIP_H)


def load_font(size):
    try:
        return pygame.font.Font(FONT, size)
    except Exception:
        return pygame.font.Font(None, size)


def fit(font, text, max_w):
    """Cut text with an ellipsis so it fits max_w pixels."""
    if font.size(text)[0] <= max_w:
        return text
    lo, hi = 0, len(text)
    while lo < hi:
        mid = (lo + hi + 1) // 2
        if font.size(text[:mid].rstrip() + "…")[0] <= max_w:
            lo = mid
        else:
            hi = mid - 1
    return text[:lo].rstrip() + "…"


def scale_to_fit(img, size):
    w, h = img.get_size()
    k = size / max(w, h)
    return pygame.transform.smoothscale(img, (max(1, int(w * k)), max(1, int(h * k))))


def fmt(sec):
    h, rem = divmod(int(sec), 3600)
    m, s = divmod(rem, 60)
    return f"{h}:{m:02}:{s:02}" if h else f"{m}:{s:02}"


def skin_strip(cfg):
    """Strip rect: the space under the current skin if big enough, else the default."""
    try:
        section = cfg[cfg[METER]]
        path = os.path.join(cfg[BASE_PATH], cfg[SCREEN_INFO][METER_FOLDER], section[BGR_FILENAME])
        bottom = int(section[METER_Y]) + pygame.image.load(path).get_height()
    except Exception as e:
        print(f"Could not measure skin ({e}); using default strip", flush=True)
        return default_strip()
    if SCREEN_H - bottom >= MIN_FREE:
        return pygame.Rect(0, bottom, SCREEN_W, SCREEN_H - bottom)
    return default_strip()


def strip_mode(cfg):
    """Per-skin strip background from meter_strip.txt: clear (default), dim or black."""
    key = f"{cfg[SCREEN_INFO][METER_FOLDER]}/{cfg[METER]}"
    try:
        with open(STRIP_FILE, encoding="utf-8") as f:
            for line in f:
                k, _, v = line.rstrip("\n").partition("\t")
                if k == key:
                    return v.strip()
    except OSError:
        pass
    return "clear"


class Layout:
    """Positions and fonts for one strip, scaled to its height."""

    def __init__(self, rect):
        self.rect = rect
        s = min(1.3, max(1.0, rect.h / 250))
        self.fonts = {k: load_font(int(v * s)) for k, v in SIZES.items()}
        self.art = min(rect.h - 30, 420)
        top = max(10, (rect.h - int(200 * s)) // 2)
        self.line_y = (top, top + int(70 * s), top + int(120 * s))
        self.bar_y = top + int(183 * s)
        self.art_top = (rect.h - self.art) // 2
        self.surface = pygame.Surface(rect.size)
        self.bgr = None
        self.text = None
        self.text_w = None
        self.small_art = None


class Overlay:
    def __init__(self, screen, play_rect):
        self.screen = screen
        self.play = Layout(play_rect)
        self.pause = Layout(default_strip())
        self.paused_font = load_font(SIZES["title"])
        self.info = {"state": "stopped"}
        self.json_mtime = None
        self.next_poll = 0.0
        self.art_key = None
        self.big_art = None
        self.last_second = None
        self.dirty = True

    def capture_background(self, mode="clear"):
        bg = self.screen.subsurface(self.play.rect).copy()
        if mode == "black":
            bg.fill(BLACK)
        elif mode == "dim":
            shade = pygame.Surface(bg.get_size())
            shade.fill(BLACK)
            shade.set_alpha(DIM_LEVEL)
            bg.blit(shade, (0, 0))
        self.play.bgr = bg
        self.dirty = True

    def state(self):
        return self.info.get("state", "stopped")

    def position(self):
        """(elapsed, length) for finite tracks, else None (radio, unknown)."""
        pos, length = self.info.get("position"), self.info.get("length")
        if pos is None or not length or length <= 0:
            return None
        if self.state() == "playing":
            pos += time.time() - self.info.get("updated", time.time())
        return min(max(pos, 0), length), length

    def tick(self):
        now = time.monotonic()
        if now >= self.next_poll:
            self.next_poll = now + POLL
            self.read_json()
        p = self.position()
        sec = int(p[0]) if p else None
        if sec != self.last_second:
            self.last_second = sec
            self.dirty = True

    def read_json(self):
        try:
            mtime = os.stat(JSON_FILE).st_mtime
            if mtime == self.json_mtime:
                return
            with open(JSON_FILE, encoding="utf-8") as f:
                info = json.load(f)
        except (OSError, ValueError):
            return
        self.json_mtime = mtime
        old, self.info = self.info, info
        if any(old.get(k) != info.get(k) for k in ("title", "artist", "album")):
            self.play.text = self.pause.text = None
        key = info.get("art_key")
        if key != info.get("image_key"):
            key = None
        if key != self.art_key:
            self.load_art(key)
        self.dirty = True

    def load_art(self, key):
        self.art_key = key
        self.play.small_art = self.big_art = None
        if not key:
            return
        try:
            img = pygame.image.load(ART_FILE).convert()
            self.play.small_art = scale_to_fit(img, self.play.art)
            self.big_art = scale_to_fit(img, BIG_ART)
        except Exception as e:
            print(f"Could not load artwork: {e}", flush=True)

    def compose(self, lay, paused):
        s = lay.surface
        if paused or lay.bgr is None:
            s.fill(BLACK)
        else:
            s.blit(lay.bgr, (0, 0))
        if self.state() == "stopped":
            return

        show_small = (not paused) and lay.small_art is not None
        max_w = lay.rect.w - 2 * MARGIN - (lay.art + 40 if show_small else 0)
        if lay.text is None or lay.text_w != max_w:
            lay.text_w = max_w
            lay.text = []
            for key, colour in (("title", WHITE), ("artist", GREY), ("album", DIM)):
                t = self.info.get(key) or ""
                f = lay.fonts[key]
                lay.text.append(f.render(fit(f, t, max_w), True, colour) if t else None)
        for surf, y in zip(lay.text, lay.line_y):
            if surf:
                s.blit(surf, (MARGIN, y))

        p = self.position()
        if p:
            pos, length = p
            t = lay.fonts["time"].render(f"{fmt(pos)} / {fmt(length)}", True, DIM)
            bar_w = min(1200, max_w - t.get_width() - 40)
            pygame.draw.rect(s, TRACK, (MARGIN, lay.bar_y, bar_w, 4))
            pygame.draw.rect(s, WHITE, (MARGIN, lay.bar_y, int(bar_w * pos / length), 4))
            s.blit(t, (MARGIN + bar_w + 24, lay.bar_y + 2 - t.get_height() // 2))

        if show_small:
            r = lay.small_art.get_rect(center=(lay.rect.w - MARGIN - lay.art // 2, lay.art_top + lay.art // 2))
            s.blit(lay.small_art, r)

    def draw_strip(self, areas):
        """Meter view: redraw the strip if needed, and repair it where PeppyMeter repainted needles."""
        rect = self.play.rect
        out = [pygame.Rect(a) for a in (areas or []) if a]
        if self.dirty:
            self.compose(self.play, False)
            self.screen.blit(self.play.surface, rect.topleft)
            out.append(rect.copy())
            self.dirty = False
        else:
            for a in out:
                r = a.clip(rect)
                if r.w and r.h:
                    self.screen.blit(self.play.surface, r.topleft, r.move(-rect.x, -rect.y))
        return out

    def draw_paused(self):
        self.screen.fill(BLACK)
        self.screen.blit(self.paused_font.render("Paused", True, WHITE), (MARGIN, 40))
        if self.big_art:
            self.screen.blit(self.big_art, self.big_art.get_rect(midtop=(self.screen.get_width() // 2, 50)))
        self.compose(self.pause, True)
        self.screen.blit(self.pause.surface, self.pause.rect.topleft)
        self.dirty = False


class FrameMeter(Peppymeter):
    def start_display_output(self):
        screen = self.util.PYGAME_SCREEN
        full = self.util.meter_config[SCREEN_RECT]
        fps = self.util.meter_config[FRAME_RATE]
        clock = Clock()
        pygame.event.clear()

        self.meter.start()
        strip = skin_strip(self.util.meter_config)
        mode = strip_mode(self.util.meter_config)
        print(f"Skin '{self.util.meter_config[METER]}': strip {tuple(strip)}, background {mode}", flush=True)
        overlay = Overlay(screen, strip)
        overlay.capture_background(mode)
        pygame.display.update(full)
        paused_view = False

        while True:
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    self.exit()

            overlay.tick()
            if overlay.state() == "paused":
                if not paused_view or overlay.dirty:
                    overlay.draw_paused()
                    pygame.display.update(full)
                    paused_view = True
            elif paused_view:
                screen.fill(BLACK)
                self.meter.start()
                overlay.dirty = True
                overlay.draw_strip(None)
                pygame.display.update(full)
                paused_view = False
            else:
                pygame.display.update(overlay.draw_strip(self.meter.run()))
                self.refresh()

            clock.tick(fps)


if __name__ == "__main__":
    pm = FrameMeter(standalone=True)
    # The screen is the configured size even when a skin folder's name says otherwise
    # (PeppyMeter takes the size from names like "1920x720-...").
    pm.util.meter_config[SCREEN_INFO][WIDTH], pm.util.meter_config[SCREEN_INFO][HEIGHT] = SCREEN_W, SCREEN_H
    if pm.util.meter_config[DATA_SOURCE][TYPE] != SOURCE_PIPE:
        pm.data_source.start_data_source()
    pm.init_display()
    print("Frame display started", flush=True)
    pm.start_display_output()
