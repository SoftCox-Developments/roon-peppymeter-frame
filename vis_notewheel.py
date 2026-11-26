#!/usr/bin/env python3
# Roon PeppyMeter Frame - VISUALISER EXTENSION - note wheel
#
# Copyright (C) 2026 Andrew Cox (SoftCox Developments)
# SPDX-License-Identifier: GPL-3.0-or-later
#
# This program is free software: you can redistribute it and/or modify it under the terms of
# the GNU General Public License as published by the Free Software Foundation, either
# version 3 of the License, or (at your option) any later version. See LICENSE.
"""The note wheel: the harmony of the music, worked out from the sound alone.

The 12 notes sit round the circle of fifths, each lit by how much of it is sounding (a
chromagram), in five rings by register: bass innermost, then octaves 3, 4 and 5, treble
outermost. The chord being played is named beside the wheel, with the key of the last
few seconds and a row of recent chords. Inside the wheel, a trail follows the chord's
centre: music that stays in one key stays on one side; music that changes key travels.

How: an FFT of the last 0.19 s; each frequency folded into its pitch class (C, C#, ... B,
octave ignored), weighted towards fundamentals; chords named by matching 60 templates
(5 types x 12 roots); the key by the Krumhansl-Kessler key profiles.

Drawn by vis_hifi_display.py as hifi/Note wheel.
"""
import colorsys
import math
import time

import numpy as np
import pygame

import vis_settings

RATE = 44100
V = vis_settings.load()
FPS = max(5, V.getint("display_fps"))
BLACK = (0, 0, 0)
GRID = (38, 48, 44)
LABEL = (120, 135, 128)
WHITE = (235, 235, 235)

FIFTHS = [0, 7, 2, 9, 4, 11, 6, 1, 8, 3, 10, 5]          # pitch classes round the wheel, C at the top
POS = {pc: i for i, pc in enumerate(FIFTHS)}
NAMES = ["C", "D♭", "D", "E♭", "E", "F", "F♯", "G", "A♭", "A", "B♭", "B"]
WHEEL_NAMES = ["C", "G", "D", "A", "E", "B", "F♯", "D♭", "A♭", "E♭", "B♭", "F"]
QUALITIES = [("", (0, 4, 7)), ("m", (0, 3, 7)), ("7", (0, 4, 7, 10)), ("maj7", (0, 4, 7, 11)), ("m7", (0, 3, 7, 10))]
TEMPLATES = []
for _root in range(12):
    for _q, _iv in QUALITIES:
        _t = np.zeros(12)
        for _v in _iv:
            _t[(_root + _v) % 12] = 1.0
        TEMPLATES.append((_root, _q, _t / np.linalg.norm(_t)))
TPL = np.array([t for _, _, t in TEMPLATES])
# Krumhansl-Kessler key profiles: how well each note fits a major / minor key on C
MAJOR = np.array([6.35, 2.23, 3.48, 2.33, 4.38, 4.09, 2.52, 5.19, 2.39, 3.66, 2.29, 2.88])
MINOR = np.array([6.33, 2.68, 3.52, 5.38, 2.60, 3.53, 2.54, 4.75, 3.98, 2.69, 3.34, 3.17])
PROFILES = [(mode, root, np.roll(p, root) - p.mean()) for mode, p in (("major", MAJOR), ("minor", MINOR)) for root in range(12)]


def pc_colour(pc, v=1.0, s=0.75):
    """A colour for a note: neighbours on the circle of fifths get neighbouring hues."""
    r, g, b = colorsys.hsv_to_rgb(POS[pc] / 12.0, s, max(0.0, min(1.0, v)))
    return int(r * 255), int(g * 255), int(b * 255)


def key_of(chroma):
    c = chroma - chroma.mean()
    nc = np.linalg.norm(c) + 1e-9
    best = (-2.0, None, None)
    for mode, root, p in PROFILES:
        r = float(np.dot(c, p) / (nc * np.linalg.norm(p)))
        if r > best[0]:
            best = (r, root, mode)
    return best


class Chroma:
    """How much of each of the 12 notes is being played, from the sound.

    The spectrum is measured on the piano's semitones (C2 to E7): a longer FFT for the low
    notes, where semitones are close together. Then two clean-ups, so the wheel shows the
    notes played rather than everything that rings:
      - overtones: each note also sounds an octave, an octave and a fifth, two octaves and
        two octaves and a third above; going up from the lowest note, what a note's
        overtones would put on the notes above it is taken off them;
      - noise: only a pitch that stands out from its neighbours counts (a peak), so the
        broadband scrape of a strum or a drum hit lights nothing.
    The 12 pitch classes are then summed (C2, C3, C4 ... all count as C). The same notes are
    also kept by register, in self.rings: bass (below C3), octaves 3, 4 and 5, and treble
    (C6 up), for the wheel's rings.
    """

    RINGS = 5

    LO, HI = 36, 100                                    # C2 .. E7 (a lower bass note still shows, by its octave)
    OVERTONES = ((12, 0.45), (19, 0.30), (24, 0.20), (28, 0.15), (31, 0.10))   # semitones up, share of power

    def __init__(self, peak_db=3.0, full_db=12.0):
        self.keys = np.arange(self.LO, self.HI + 1)
        self.k = len(self.keys)
        freqs = 440.0 * 2 ** ((self.keys - 69) / 12.0)
        self.parts = []
        for n, sel in ((16384, self.keys < 52), (8192, self.keys >= 52)):
            f = np.fft.rfftfreq(n, 1.0 / RATE)
            idx = []
            for fk in freqs[sel]:
                b = np.nonzero((f >= fk * 2 ** (-0.5 / 12)) & (f < fk * 2 ** (0.5 / 12)))[0]
                idx.append(b if len(b) else np.array([int(round(fk / (RATE / n)))]))
            self.parts.append((n, np.hanning(n).astype(np.float32), np.nonzero(sel)[0], idx))
        self.pc = self.keys % 12
        self.peak_db, self.span_db = peak_db, max(1.0, full_db - peak_db)
        self.weight = 1.0 / np.sqrt(freqs / freqs[0])    # lean a little towards the lower, fundamental notes
        self.ring = np.clip(self.keys // 12 - 3, 0, self.RINGS - 1)            # MIDI octave - 2: bass, 3, 4, 5, treble
        self.lift = 10 ** (3.0 / 20 * (self.keys - 60) / 12.0)                  # +3 dB an octave, so treble shows
        self.rings = np.zeros((self.RINGS, 12))

    def __call__(self, mono):
        p = np.zeros(self.k)
        for n, win, which, idx in self.parts:
            spec = np.abs(np.fft.rfft(mono[-n:] * win)) ** 2 / (n * n)
            for j, b in zip(which, idx):
                p[j] = spec[b].max()
        for j in range(self.k):                          # take away the overtones of lower notes
            if p[j] > 0:
                for off, share in self.OVERTONES:
                    if j + off < self.k:
                        p[j + off] = max(0.0, p[j + off] - share * p[j])
        db = 10 * np.log10(p + 1e-20)
        around = np.median(np.lib.stride_tricks.sliding_window_view(np.pad(db, 6, mode="edge"), 13), axis=1)
        peak = np.clip((db - around - self.peak_db) / self.span_db, 0.0, 1.0)
        amp = np.sqrt(p) * peak
        self.rings = np.zeros((self.RINGS, 12))
        np.add.at(self.rings, (self.ring, self.pc), amp * self.lift)
        return np.bincount(self.pc, weights=amp * self.weight, minlength=12)


class NoteWheel:
    def __init__(self, screen, area, font):
        self.screen, self.area = screen, area
        self.chroma = Chroma()
        self.trail_len = max(1, int(V.getfloat("wheel_trail_seconds") * FPS))
        self.key_frames = max(1.0, V.getfloat("wheel_key_seconds") * FPS)
        self.match = V.getfloat("wheel_chord_match")
        self.follow = 1 - math.exp(-1.0 / (FPS * max(0.02, V.getfloat("wheel_smoothing"))))
        self.floor = min(0.9, max(0.0, V.getfloat("wheel_note_floor")))
        self.log = V.get("wheel_log").lower() in ("yes", "on", "true", "1")
        self.by_register = V.get("wheel_rings").lower() not in ("no", "off", "false", "0")
        self.reset()
        k = area.h / 720.0
        self.k = k
        self.cx, self.cy = area.x + int(60 * k) + area.h // 2, area.y + area.h // 2
        self.r_out, self.r_in = int(area.h * 0.43), int(area.h * 0.26)
        self.r_trail = self.r_in - int(18 * k)
        self.ang = [math.radians(-90 + 30 * i) for i in range(12)]
        self.font = font
        bold = lambda size: font(size, True)
        self.labels = [bold(int(34 * k)).render(n, True, LABEL) for n in WHEEL_NAMES]
        x = self.cx + self.r_out + int(170 * k)
        room = area.right - int(30 * k) - x                 # width beside the wheel for the names

        def fitted(make, size, widest):                     # the largest size up to `size` where `widest` fits
            f = make(size)
            w = f.size(widest)[0]
            return f if w <= room else make(max(10, int(size * room / w)))
        self.f_chord = fitted(bold, int(150 * k), "E\u266dmaj7")
        self.f_key = fitted(font, int(64 * k), "\u2014 wandering \u2014")
        self.f_chip = bold(int(40 * k))
        small = font(int(28 * k))
        self.captions = [(small.render(t, True, LABEL), y) for t, y in
                         (("chord", 40), ("key, last few seconds", 290), ("recent chords", 480))]
        def arc(i, r0, r1):                                 # one segment of the wheel between two radii
            a0, a1 = self.ang[i] - math.radians(14), self.ang[i] + math.radians(14)
            outer = [(self.cx + r1 * math.cos(a0 + (a1 - a0) * j / 8), self.cy + r1 * math.sin(a0 + (a1 - a0) * j / 8)) for j in range(9)]
            inner = [(self.cx + r0 * math.cos(a0 + (a1 - a0) * j / 8), self.cy + r0 * math.sin(a0 + (a1 - a0) * j / 8)) for j in range(8, -1, -1)]
            return outer + inner
        self.segments = [arc(i, self.r_in, self.r_out) for i in range(12)]
        # registers, bass innermost: each segment is drawn as thin slices, their brightness blended
        # between the registers' centres, so the light grades smoothly from ring to ring
        n, slices = Chroma.RINGS, 15
        dr = (self.r_out - self.r_in) / slices
        self.slice_arcs = [[arc(i, self.r_in + j * dr, self.r_in + (j + 1) * dr + 0.6) for j in range(slices)] for i in range(12)]
        centres = (np.arange(n) + 0.5) / n
        self.blend = np.array([np.interp((j + 0.5) / slices, centres, np.eye(n)[r]) for j in range(slices) for r in range(n)]).reshape(slices, n)
        self.chip_cache = {}

    def reset(self):
        self.c = np.zeros(12)                           # brightness of each note as drawn, 0..1
        self.shape = np.zeros(12)                       # each note's share, the strongest = 1, smoothed
        self.cells = np.zeros((Chroma.RINGS, 12))       # the same, by register (bass .. treble)
        self.lit = np.zeros((Chroma.RINGS, 12))         # brightness of each ring of each note as drawn
        self.slow = np.full(12, 1e-6)
        self.loud = 0.0
        self.trail = []
        self.z = None
        self.chord = None
        self.cand, self.cand_n = None, 0
        self.quiet = 0
        self.history = []
        self.key = None
        self.shown_key = None

    @staticmethod
    def chord_tones(chord):
        root, q = chord
        w = np.zeros(12)
        for v in dict(QUALITIES)[q]:
            w[(root + v) % 12] = 1.0
        w[root] = 1.5                                   # lean towards the root
        return w

    def update(self, audio):
        mono = (audio.left + audio.right) * 0.5
        raw = self.chroma(mono)
        rms = math.sqrt(float(np.mean(mono[-4096:] ** 2)) + 1e-9) / 32768.0
        loud = min(1.0, max(0.0, (20 * math.log10(rms + 1e-12) + 54.0) / 42.0))   # -54 .. -12 dB
        self.loud += (loud - self.loud) * 0.3
        shape = raw / (raw.max() + 1e-9) if raw.max() > 0 else raw
        self.shape += (shape - self.shape) * self.follow
        # only notes near the strongest light up: weaker ones stay dark
        self.c = np.clip((self.shape - self.floor) / (1.0 - self.floor), 0.0, 1.0) ** 1.2 * self.loud
        if self.by_register:
            rings = self.chroma.rings
            top = rings.max()
            self.cells += ((rings / top if top > 0 else rings) - self.cells) * self.follow
            self.lit = np.clip((self.cells - self.floor) / (1.0 - self.floor), 0.0, 1.0) ** 1.2 * self.loud
        self.slow += (shape * self.loud - self.slow) / self.key_frames
        # the chord, with a little patience so the name doesn't flicker
        best = None
        if self.loud > 0.1:
            v = self.shape / (np.linalg.norm(self.shape) + 1e-9)
            scores = TPL @ v
            i = int(np.argmax(scores))
            if scores[i] > self.match:
                best = (TEMPLATES[i][0], TEMPLATES[i][1])
        if best == self.cand:
            self.cand_n += 1
        else:
            self.cand, self.cand_n = best, 1
        if best and self.cand_n == 4 and best != self.chord:
            self.chord = best                               # a chord stays named until the next one is sure
            self.history = (self.history + [best])[-8:]
        self.quiet = self.quiet + 1 if self.loud <= 0.1 else 0
        if self.quiet > FPS:                                # a second of near silence clears the name
            self.chord = None
        r, root, mode = key_of(self.slow)
        self.key = (root, mode, r) if self.slow.sum() > 0.3 else None
        # the trail: the centre of the chord on the wheel (the raw notes when no chord is named)
        w = self.chord_tones(self.chord) if (self.chord and self.loud > 0.1) else self.c ** 3
        if w.sum() > 0.01:
            z = sum(w[pc] * complex(math.cos(self.ang[POS[pc]]), math.sin(self.ang[POS[pc]])) for pc in range(12)) / w.sum()
            z *= 1.6
            if abs(z) > 0.95:
                z *= 0.95 / abs(z)
            self.z = z if self.z is None else self.z + (z - self.z) * 0.35
            self.trail.append((self.z, self.chord[0] if self.chord else None))
        else:
            self.z = None
            self.trail.append(None)
        del self.trail[:-self.trail_len]
        if self.log:
            self.write_log()

    def key_text(self):
        if not self.key:
            return None
        root, mode, r = self.key
        return f"{NAMES[root]} {mode}" if r > 0.55 else "wandering"

    def write_log(self):
        """With wheel_log = yes: each new chord and key goes to the journal (journalctl -u rpf-vis)."""
        name = (NAMES[self.chord[0]] + self.chord[1]) if self.chord else "-"
        key = self.key_text() or "-"
        if (name, key) != getattr(self, "_logged", None):
            self._logged = (name, key)
            print(f"{time.strftime('%H:%M:%S')} chord {name:7s} key {key}", flush=True)

    def chip(self, chord):
        if chord not in self.chip_cache:
            root, q = chord
            t = self.f_chip.render(NAMES[root] + q, True, BLACK)
            pad = int(12 * self.k)
            surf = pygame.Surface((t.get_width() + 2 * pad, int(60 * self.k)), pygame.SRCALPHA)
            pygame.draw.rect(surf, pc_colour(root, 0.85, 0.6), surf.get_rect(), border_radius=int(10 * self.k))
            surf.blit(t, (pad, (surf.get_height() - t.get_height()) // 2))
            self.chip_cache[chord] = surf
        return self.chip_cache[chord]

    def draw(self, audio):
        self.update(audio)
        s, a, k = self.screen, self.area, self.k
        s.fill(BLACK, a)
        cx, cy = self.cx, self.cy
        if self.by_register:
            self.shade = self.blend @ self.lit              # brightness of each slice of each note
        for i, pc in enumerate(FIFTHS):
            if self.by_register:
                glow = 0.4 * float(self.c[pc])             # the whole note glows dimly; its registers brighter
                for j, poly in enumerate(self.slice_arcs[i]):
                    v = max(glow, float(self.shade[j, pc]))
                    pygame.draw.polygon(s, pc_colour(pc, 0.10 + 0.9 * v ** 0.8), poly)
            else:
                pygame.draw.polygon(s, pc_colour(pc, 0.10 + 0.9 * float(self.c[pc]) ** 0.8), self.segments[i])
            pygame.draw.polygon(s, pc_colour(pc, 0.35, 0.4), self.segments[i], 1)
            lab = self.labels[i]
            d = self.r_out + 34 * k
            s.blit(lab, (cx + d * math.cos(self.ang[i]) - lab.get_width() / 2,
                         cy + d * math.sin(self.ang[i]) - lab.get_height() / 2))
        pygame.draw.circle(s, GRID, (cx, cy), self.r_trail, 1)
        pts = [None if e is None else (cx + e[0].real * self.r_trail, cy + e[0].imag * self.r_trail) for e in self.trail]
        n = len(pts)
        for j in range(1, n):
            p, q = pts[j - 1], pts[j]
            if p and q:
                f = j / n
                root = self.trail[j][1]
                col = pc_colour(root, 0.25 + 0.75 * f, 0.55) if root is not None else (int(90 * f),) * 3
                pygame.draw.line(s, col, p, q, 1 + int(4 * f * k))
        if pts and pts[-1]:
            pygame.draw.circle(s, WHITE, (int(pts[-1][0]), int(pts[-1][1])), int(9 * k))
        # chord, key and recent chords
        x = cx + self.r_out + int(170 * k)
        for surf, y in self.captions:
            s.blit(surf, (x + 6 * k, a.y + y * k))
        if self.chord:
            root, q = self.chord
            s.blit(self.f_chord.render(NAMES[root] + q, True, pc_colour(root, 1.0, 0.55)), (x, a.y + 70 * k))
        text = self.key_text()
        if text:
            col = pc_colour(self.key[0], 0.95, 0.45) if text != "wandering" else LABEL
            s.blit(self.f_key.render(text if text != "wandering" else "— wandering —", True, col), (x, a.y + 325 * k))
        chips, room = [], a.right - 20 * k - x           # the newest chords that fit, oldest on the left
        for chord in reversed(self.history):
            surf = self.chip(chord)
            if surf.get_width() > room:
                break
            chips.insert(0, surf)
            room -= surf.get_width() + int(12 * k)
        cxp = x
        for surf in chips:
            s.blit(surf, (cxp, a.y + 520 * k))
            cxp += surf.get_width() + int(12 * k)
        return [a]
