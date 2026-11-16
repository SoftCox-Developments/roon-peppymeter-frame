#!/usr/bin/env python3
# Roon PeppyMeter Frame - VISUALISER EXTENSION - hi-fi displays
#
# Copyright (C) 2026 Andrew Cox (SoftCox Developments)
# SPDX-License-Identifier: GPL-3.0-or-later
#
# This program is free software: you can redistribute it and/or modify it under the terms of
# the GNU General Public License as published by the Free Software Foundation, either
# version 3 of the License, or (at your option) any later version. See LICENSE.
"""Three displays that are direct pictures of the sound, drawn from the audio itself:

  hifi/Oscilloscope   the waveform of the left and right channels, as on a scope
  hifi/Goniometer     the stereo image (vectorscope): mono is a vertical line, wide stereo
                      fills out, out-of-phase sound lies sideways; with a phase meter
  hifi/Waterfall      the spectrum scrolling by: time runs right to left, pitch bottom to
                      top, brightness is loudness - notes, tunes and drum hits become shapes

They read the audio hub's raw feed (/tmp/rpf_pcm) and share the now-playing strip and the
paused screen with the other displays. With 'vis strip off' they fill the whole screen.

Started by vis_spectrum_display.py when the chosen visualiser is hifi/<name>.
  --snapshot FILE SECONDS   save the screen to FILE after SECONDS and exit (testing)
"""
import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import vis_settings
import vis_spectrum_display as vsd          # brings in frame_display (strip, paused screen)
from frame_display import Overlay, BLACK, FONT, SCREEN_W, SCREEN_H

import numpy as np
import pygame
from pygame.time import Clock

NAMES = ("Oscilloscope", "Goniometer", "Waterfall")
V = vis_settings.load()
FPS = max(5, V.getint("display_fps"))
RATE = 44100
GAIN = 10 ** (V.getfloat("hifi_gain_db") / 20.0)
GRID = (38, 48, 44)
LABEL = (120, 135, 128)


def font(size):
    try:
        return pygame.font.Font(FONT, size)
    except Exception:
        return pygame.font.Font(None, size)


class Audio:
    """The most recent audio from the hub, read without ever waiting for it."""

    def __init__(self, keep=16384):
        vsd.ensure_fifo(vis_settings.PCM_PIPE)
        self.fd = os.open(vis_settings.PCM_PIPE, os.O_RDONLY | os.O_NONBLOCK)
        self.keep = keep
        self.left = np.zeros(keep, dtype=np.float32)
        self.right = np.zeros(keep, dtype=np.float32)
        self.rest = b""
        self.new = 0                # frames that arrived in the last read()

    def read(self):
        chunks = [self.rest]
        try:
            while True:
                data = os.read(self.fd, 65536)
                if not data:
                    break
                chunks.append(data)
                if len(data) < 65536:
                    break
        except (BlockingIOError, InterruptedError):
            pass
        data = b"".join(chunks)
        usable = len(data) - len(data) % 4
        self.rest = data[usable:]
        self.new = 0
        if not usable:
            return
        s = np.frombuffer(data[:usable], dtype=np.int16).astype(np.float32)
        n = min(len(s) // 2, self.keep)
        self.new = n
        for buf, ch in ((self.left, s[0::2]), (self.right, s[1::2])):
            buf[:-n] = buf[n:]
            buf[-n:] = ch[-n:]


class Oscilloscope:
    """Left and right waveforms, triggered on a rising zero crossing so the picture holds
    still, with the two previous sweeps left faintly behind as afterglow."""

    def __init__(self, screen, area):
        self.screen, self.area = screen, area
        self.win = max(64, int(RATE * V.getfloat("scope_ms") / 1000.0))
        self.x = np.linspace(area.x + 8, area.right - 8, self.win)
        half = area.h // 2
        self.rows = [(area.y + half // 2, (90, 255, 170)), (area.y + half + half // 2, (255, 190, 70))]
        self.amp = (half / 2 - 14) / 32768.0 * GAIN
        self.trails = [[], []]
        self.kernel = np.ones(48, dtype=np.float32) / 48      # about 1 ms: smooths the trigger signal
        self.look = 40
        self.last = self.win // 2
        f = font(26)
        self.labels = [f.render("L", True, LABEL), f.render("R", True, LABEL)]

    def draw(self, audio):
        a, s = self.area, self.screen
        s.fill(BLACK, a)
        for cy, _ in self.rows:
            pygame.draw.line(s, GRID, (a.x, cy), (a.right, cy))
        for i in range(1, 10):
            x = a.x + a.w * i // 10
            pygame.draw.line(s, GRID, (x, a.y + 6), (x, a.bottom - 6))
        pygame.draw.line(s, GRID, (a.x, a.centery), (a.right, a.centery))
        # Trigger, so the picture holds still: start the sweep where the smoothed signal (which
        # follows the bass and ignores treble wiggles) crosses zero going up. Of the crossings
        # on offer take the one with the biggest swing after it, and if the place found last
        # frame's distance away is nearly as good, stay there - fewer sideways jumps.
        mono = audio.left + audio.right
        lo, hi = len(mono) - 2 * self.win, len(mono) - self.win
        smooth = np.convolve(mono[lo - 64:hi + 64], self.kernel, mode="same")[64:-64]
        cross = np.nonzero((smooth[:-1] < 0) & (smooth[1:] >= 0))[0]
        if len(cross):
            ahead = np.minimum(cross + self.look, len(smooth) - 1)
            swing = smooth[ahead] - smooth[np.maximum(cross - self.look, 0)]
            best = int(np.argmax(swing))
            near = int(np.argmin(np.abs(cross - self.last)))
            pick = near if swing[near] >= 0.8 * swing[best] else best
            self.last = int(cross[pick])
        start = lo + self.last + 1
        for k, (ch, (cy, colour)) in enumerate(zip((audio.left, audio.right), self.rows)):
            y = np.clip(cy - ch[start:start + self.win] * self.amp, a.y, a.bottom - 1)
            pts = np.column_stack((self.x, y)).tolist()
            trail = self.trails[k]
            for age, old in enumerate(trail):
                shade = 0.22 + 0.16 * age
                pygame.draw.lines(s, tuple(int(c * shade) for c in colour), False, old, 1)
            pygame.draw.lines(s, colour, False, pts, 2)
            trail.append(pts)
            if len(trail) > 2:
                trail.pop(0)
            s.blit(self.labels[k], (a.x + 16, cy - (a.h // 4) + 10))
        return [a]


class Goniometer:
    """Stereo vectorscope with phosphor-style decay, and a phase correlation meter."""

    def __init__(self, screen, area):
        self.screen, self.area = screen, area
        self.side = side = min(area.h - 40, area.w - 400) // 2 * 2
        self.pane_rect = pygame.Rect(0, 0, side, side)
        self.pane_rect.center = area.center
        self.pane = pygame.Surface((side, side), 0, 8)
        self.pane.set_palette([(int(20 * min(1, v / 60)), min(255, int(v * 1.15)), int(60 + v * 0.55) if v else 0)
                               if v else (0, 0, 0) for v in range(256)])
        decay = min(0.98, max(0.3, V.getfloat("gonio_decay")))
        self.lut = (np.arange(256) * decay).astype(np.uint8)
        self.k = 1.8 * side / (4 * 32768.0) * GAIN      # music rarely nears full scale on both channels at once
        self.corr = 0.0
        f = font(24)
        self.text = {t: f.render(t, True, LABEL) for t in ("L", "R", "M", "+1", "0", "-1", "PHASE")}
        self.meter = pygame.Rect(self.pane_rect.right + 90, self.pane_rect.y + 40, 26, side - 80)
        self.dirty = self.pane_rect.union(self.meter.inflate(120, 90)).clip(area)
        self.first = True

    def draw(self, audio):
        s, pr = self.screen, self.pane_rect
        n = min(audio.new, 4096)
        arr = pygame.surfarray.pixels2d(self.pane)
        np.take(self.lut, arr, out=arr)
        if n:
            l, r = audio.left[-n:], audio.right[-n:]
            half = self.side // 2
            x = np.clip((half + (r - l) * self.k).astype(np.intp), 0, self.side - 2)
            y = np.clip((half - (l + r) * self.k).astype(np.intp), 0, self.side - 2)
            arr[x, y] = 255
            arr[x + 1, y] = 255
            arr[x, y + 1] = 255
            arr[x + 1, y + 1] = 255
        del arr
        if self.first:
            s.fill(BLACK, self.area)
        s.blit(self.pane, pr)
        pygame.draw.line(s, GRID, pr.topleft, pr.bottomright)
        pygame.draw.line(s, GRID, pr.topright, pr.bottomleft)
        pygame.draw.line(s, GRID, pr.midtop, pr.midbottom)
        pygame.draw.rect(s, GRID, pr, 1)
        s.blit(self.text["L"], (pr.x + 10, pr.y + 6))
        s.blit(self.text["R"], (pr.right - 10 - self.text["R"].get_width(), pr.y + 6))
        s.blit(self.text["M"], (pr.centerx + 8, pr.y + 6))

        # phase correlation over the last tenth of a second: +1 mono, 0 unrelated, -1 out of phase
        l, r = audio.left[-4410:], audio.right[-4410:]
        power = float(np.sqrt(np.dot(l, l) * np.dot(r, r)))
        target = float(np.dot(l, r)) / power if power > 1e3 else 0.0
        self.corr += (target - self.corr) * 0.25
        m = self.meter
        s.fill(BLACK, m.inflate(120, 90).clip(self.area))
        pygame.draw.rect(s, GRID, m, 1)
        h = int((m.h // 2 - 2) * abs(self.corr))
        if self.corr >= 0:
            s.fill((90, 255, 170), (m.x + 3, m.centery - h, m.w - 6, h))
        else:
            s.fill((255, 80, 60), (m.x + 3, m.centery, m.w - 6, h))
        pygame.draw.line(s, LABEL, (m.x - 6, m.centery), (m.right + 6, m.centery))
        s.blit(self.text["+1"], (m.right + 14, m.y - 4))
        s.blit(self.text["0"], (m.right + 14, m.centery - 14))
        s.blit(self.text["-1"], (m.right + 14, m.bottom - 24))
        s.blit(self.text["PHASE"], (m.centerx - self.text["PHASE"].get_width() // 2, m.bottom + 10))
        if self.first:
            self.first = False
            return [self.area]
        return [self.dirty]


class Waterfall:
    """Scrolling spectrogram: each frame adds a column on the right, one row per pitch."""

    def __init__(self, screen, area):
        import vis_audio_hub as hub                 # for its band maths, so levels match the spectrum bars
        self.screen, self.area = screen, area
        self.bands = hub.Bands(area.h, RATE)
        self.n = self.bands.n
        self.pane = pygame.Surface(area.size, 0, 8)
        self.pane.set_palette(self.palette())
        self.per_frame = area.w / (max(2.0, V.getfloat("waterfall_seconds")) * FPS)
        self.owed = 0.0
        f = font(22)
        edges = self.bands.edges
        self.marks = []
        for hz, text in ((50, "50"), (100, "100"), (200, "200"), (500, "500"), (1000, "1k"), (2000, "2k"), (5000, "5k"), (10000, "10k")):
            if edges[0] < hz < edges[-1]:
                row = math.log(hz / edges[0]) / math.log(edges[-1] / edges[0]) * area.h
                self.marks.append((area.bottom - int(row), f.render(text, True, (235, 235, 235))))

    @staticmethod
    def palette():
        # black, then blues bright enough to see against it, purple, red, orange, yellow, white
        stops = [(0, (0, 0, 0)), (25, (20, 25, 95)), (70, (40, 80, 205)), (115, (150, 55, 190)), (160, (230, 60, 90)),
                 (205, (255, 160, 30)), (238, (255, 235, 110)), (255, (255, 255, 255))]
        out = []
        for v in range(256):
            for (a, ca), (b, cb) in zip(stops, stops[1:]):
                if a <= v <= b:
                    t = (v - a) / (b - a)
                    out.append(tuple(int(ca[i] + (cb[i] - ca[i]) * t) for i in range(3)))
                    break
        return out

    def draw(self, audio):
        self.owed += self.per_frame
        px = int(self.owed)
        self.owed -= px
        if px:
            mono = (audio.left[-self.n:] + audio.right[-self.n:]) * (0.5 * GAIN)
            column = (self.bands.levels(mono)[::-1] * 2.55).astype(np.uint8)
            self.pane.scroll(-px, 0)
            arr = pygame.surfarray.pixels2d(self.pane)
            arr[-px:, :] = column[np.newaxis, :]
            del arr
        a = self.area
        self.screen.blit(self.pane, a)
        for y, label in self.marks:
            pygame.draw.line(self.screen, (235, 235, 235), (a.x, y), (a.x + 10, y))
            self.screen.blit(label, (a.x + 16, y - label.get_height() // 2))
        return [a]


def main():
    snapshot = None
    if len(sys.argv) == 4 and sys.argv[1] == "--snapshot":
        snapshot = (sys.argv[2], float(sys.argv[3]))
    folder, name = vsd.current_skin()
    if folder != "hifi" or name not in NAMES:
        vsd.die(f"'{folder}/{name}' is not a hi-fi display ({', '.join(NAMES)})")

    pygame.display.init()           # not pygame.init(): that would also open a sound device
    pygame.font.init()
    screen = pygame.display.set_mode((SCREEN_W, SCREEN_H), pygame.NOFRAME | pygame.DOUBLEBUF)
    pygame.mouse.set_visible(False)
    full = screen.get_rect()
    mode = vsd.strip_mode(folder, name, "clear")
    top_h = SCREEN_H if mode == "off" else SCREEN_H * 2 // 3
    area = pygame.Rect(0, 0, SCREEN_W, top_h)
    strip = pygame.Rect(0, top_h, SCREEN_W, SCREEN_H - top_h) if mode != "off" else pygame.Rect(0, SCREEN_H - 250, SCREEN_W, 250)
    screen.fill(BLACK)
    overlay = Overlay(screen, strip)
    if mode != "off":
        overlay.capture_background(mode)
    audio = Audio()
    display = {"Oscilloscope": Oscilloscope, "Goniometer": Goniometer, "Waterfall": Waterfall}[name](screen, area)
    print(f"Hi-fi display '{name}': area {tuple(area)}, strip {mode}, {FPS} fps", flush=True)
    pygame.display.update(full)

    clock = Clock()
    paused_view = False
    frames = 0
    pygame.event.clear()
    while True:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                sys.exit(0)
        audio.read()
        overlay.tick()
        if overlay.state() == "paused":
            if not paused_view or overlay.dirty:
                overlay.draw_paused()
                pygame.display.update(full)
                paused_view = True
        elif paused_view:
            screen.fill(BLACK)
            if hasattr(display, "first"):
                display.first = True
            display.draw(audio)
            overlay.dirty = True
            if mode != "off":
                overlay.draw_strip(None)
            pygame.display.update(full)
            paused_view = False
        else:
            areas = display.draw(audio)
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
