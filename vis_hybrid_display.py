#!/usr/bin/env python3
# Roon PeppyMeter Frame - VISUALISER EXTENSION - meter + spectrum skins
#
# Copyright (C) 2026 Andrew Cox (SoftCox Developments)
# SPDX-License-Identifier: GPL-3.0-or-later
#
# This program is free software: you can redistribute it and/or modify it under the terms of
# the GNU General Public License as published by the Free Software Foundation, either
# version 3 of the License, or (at your option) any later version. See LICENSE.
#
# Builds on PeppyMeter and PeppySpectrum (https://github.com/project-owner, both
# GPL-3.0-or-later), which are used unmodified.
"""Show a meter + spectrum skin: needles and spectrum bars together in one design, with
the cover art, title, artist, album and time placed where the skin wants them.

These skins were made by Gelo5 for the PeppyMeter screensaver plugin for Volumio. Their
meters.txt carries extra keys saying where everything goes (albumart.pos,
playinfo.title.pos, time.remaining.pos, spectrum.name, ...), which this program reads.
It does not use the now-playing strip: the skin has its own places for the details.

What goes in the skin's boxes:
  time box        time remaining for tracks (or elapsed: time_display = elapsed); the
                  time of day (24 hour) for radio and anything else without a length
  format badge    the picture named by format_image in [vis] of settings.conf
  resolution      the text given by format_text there, e.g. DSD 1024
Both are left empty when not set.

Started by vis_spectrum_display.py when the chosen visualiser is one of these skins.
  --snapshot FILE SECONDS   save the screen to FILE after SECONDS and exit (testing)
"""
import configparser
import glob
import math
import os
import re
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import rpf_settings
import vis_settings
import vis_spectrum_display as vsd          # also brings in frame_display and PeppyMeter's folder
from frame_display import Overlay, default_strip, fit, BLACK, FONT, SCREEN_W, SCREEN_H, ART_FILE

import pygame
from pygame.time import Clock

V = vis_settings.load()
BARS = vis_settings.DEFAULT_BARS             # these skins are all drawn for 20 bars
METER_RUN_DIR = os.path.join(vis_settings.RUN_DIR, "meter")


def read_skin(pack, folder, name):
    """The skin's section of meters.txt as a dict (keys as written, values stripped)."""
    path = os.path.join(pack, "templates", folder, "meters.txt")
    c = configparser.ConfigParser(interpolation=None, strict=False)
    c.optionxform = str
    with open(path, encoding="utf-8", errors="replace") as f:
        c.read_string(f.read().replace("\r", ""))
    if name not in c:
        vsd.die(f"No skin '{name}' in {path}")
    return {k: v.strip() for k, v in c[name].items()}


def ints(text, n):
    """First n comma-separated integers of text, or None."""
    try:
        parts = [int(p.strip()) for p in text.split(",")[:n]]
        return parts if len(parts) == n else None
    except (AttributeError, ValueError):
        return None


def colour(text, default):
    c = ints(text, 3)
    return tuple(max(0, min(255, v)) for v in c) if c else default


def flag(text):
    return str(text).strip().lower() in ("true", "yes", "1", "on")


def write_meter_config(folder, name, base):
    """PeppyMeter reads config.txt from the current folder: give it a copy of the meters'
    own with this skin, so the meters' settings (pipe, frame rate, screen) stay the same."""
    with open(os.path.join(rpf_settings.PEPPY_DIR, "config.txt"), encoding="utf-8") as f:
        text = f.read()
    for key, value in (("meter", name), ("meter.folder", folder), ("base.folder", base),
                       ("screen.width", SCREEN_W), ("screen.height", SCREEN_H)):
        text, n = re.subn(rf"(?m)^{re.escape(key)}[ \t]*=.*$", lambda m: f"{key} = {value}", text, count=1)
        if not n:
            text = text.replace("[current]", f"[current]\n{key} = {value}", 1)
    os.makedirs(METER_RUN_DIR, exist_ok=True)
    with open(os.path.join(METER_RUN_DIR, "config.txt"), "w", encoding="utf-8") as f:
        f.write("# Written by vis_hybrid_display.py at every start - edits are lost.\n" + text)


def font_file(style):
    """Text fonts: the display font, and its bold version when there is one beside it."""
    if style == "bold":
        root, ext = os.path.splitext(FONT)
        if os.path.isfile(root + "-Bold" + ext):
            return root + "-Bold" + ext
    return FONT


def digit_font(size):
    """The seven-segment font these skins were drawn for, or a plain one if it is missing."""
    for path in sorted(glob.glob(os.path.join(vis_settings.FONT_DIR, "DSEG7Classic-Italic.ttf"))
                       + glob.glob("/usr/share/fonts/truetype/**/DSEG7Classic-Italic.ttf", recursive=True)):
        try:
            return pygame.font.Font(path, size)
        except Exception:
            pass
    return load(font_file("bold"), size)


def load(path, size):
    try:
        return pygame.font.Font(path, size)
    except Exception:
        return pygame.font.Font(None, size)


def cover(img, w, h):
    """Scale and crop img to fill w x h exactly."""
    iw, ih = img.get_size()
    k = max(w / iw, h / ih)
    img = pygame.transform.smoothscale(img, (max(w, round(iw * k)), max(h, round(ih * k))))
    r = pygame.Rect(0, 0, w, h)
    r.center = img.get_rect().center
    return img.subsurface(r).copy()


def contain(img, w, h):
    iw, ih = img.get_size()
    k = min(w / iw, h / ih)
    return pygame.transform.smoothscale(img, (max(1, round(iw * k)), max(1, round(ih * k))))


class Item:
    """One thing drawn at a place the skin names: a rectangle and what is in it now."""

    def __init__(self, rect):
        self.rect = rect
        self.shown = None           # a key describing what is drawn there


class Hybrid:
    def __init__(self, pm, pack, folder, name, snapshot):
        self.pm, self.snapshot = pm, snapshot
        self.screen = pm.util.PYGAME_SCREEN
        self.full = self.screen.get_rect()
        self.skin = read_skin(pack, folder, name)
        self.dir = os.path.join(pack, "templates", folder)
        self.meter_on = flag(self.skin.get("meter.visible", "True"))
        self.spec_on = flag(self.skin.get("spectrum.visible", "False")) and self.skin.get("spectrum.name")
        self.overlay = Overlay(self.screen, default_strip())      # reads Roon's details; draws the paused screen
        self.remaining = V.get("time_display").lower() != "elapsed"
        self.art_key = None
        self.art = None
        self.fgr = None
        self.meter_bg = None
        self.meter_origin = (0, 0)

        # 1. Everything that never changes: the skin's picture, the meter's face, the spectrum's panel
        self.screen.fill(BLACK)
        self.blit_file(self.skin.get("screen.bgr"), (0, 0))
        if self.meter_on:
            xy = (int(self.skin.get("meter.x", 0) or 0), int(self.skin.get("meter.y", 0) or 0))
            self.blit_file(self.skin.get("bgr.filename"), xy)
        self.sp = None
        self.spec_rect = None
        if self.spec_on:
            self.start_spectrum(pack, folder)
        self.base = self.screen.copy()
        self.static = self.base.copy()          # base + the details as they are now

        # 2. Where the details go
        self.items = {}
        self.fonts = {}
        self.plan()

        # 3. The needles. PeppyMeter repairs the picture behind a moving needle from the
        #    meter's background image; give it ours, which includes the details.
        if self.meter_on:
            pm.meter.start()
            m = pm.meter.meter
            self.meter_origin = (m.origin_x, m.origin_y)
            self.meter_bg = pygame.Surface(m.bgr.content[1].get_size())
            self.meter_bg.blit(self.static, (0, 0), pygame.Rect(self.meter_origin, self.meter_bg.get_size()))
            m.bgr.content = (m.bgr.content[0], self.meter_bg)
            if m.fgr:
                self.fgr = m.fgr.content[1]
        print(f"Skin '{folder}/{name}': meters {'on' if self.meter_on else 'off'}, "
              f"spectrum {'on ' + str(tuple(self.spec_rect)) if self.sp else 'off'}, "
              f"{len(self.items)} places for details", flush=True)

    # -- set-up -------------------------------------------------------------------------

    def blit_file(self, filename, xy):
        if not filename:
            return
        try:
            self.screen.blit(pygame.image.load(os.path.join(self.dir, filename)).convert_alpha(), xy)
        except Exception as e:
            print(f"Could not load {filename}: {e}", flush=True)

    def start_spectrum(self, pack, folder):
        size = ints(self.skin.get("spectrum.size", ""), 2)
        pipe = vis_settings.spectrum_pipe(BARS)
        vsd.ensure_fifo(pipe)
        vsd.write_config(folder, self.skin["spectrum.name"], BARS, pipe, base=os.path.join(pack, "templates_spectrum"))
        os.chdir(vis_settings.RUN_DIR)
        sys.path.insert(0, vis_settings.SPECTRUM_DIR)
        from spectrum import Spectrum
        import spectrumconfigparser as K
        screen = self.screen

        class Embedded(Spectrum):
            def init_display(self):                 # the screen is already open
                self.util.pygame_screen = screen

            def get_backgrounds(self):              # as in vis_spectrum_display.py: no background -> black
                out, all_configs = [], self.spectrum_configs
                for config in all_configs:
                    self.spectrum_configs = [config]
                    try:
                        got = super().get_backgrounds()
                    except Exception:
                        got = []
                    out.append(got[0] if got and got[0] is not None else None)
                self.spectrum_configs = all_configs
                return out

        try:
            sp = Embedded(None, True)
        except Exception as e:
            print(f"Spectrum '{self.skin['spectrum.name']}' could not be loaded ({e}); showing the skin without it", flush=True)
            return
        cfg = sp.spectrum_configs[0]
        if size:
            sp.config[K.SCREEN_WIDTH], sp.config[K.SCREEN_HEIGHT] = size
        else:
            size = (cfg[K.BAR_WIDTH] + cfg[K.BAR_GAP]) * BARS + 2 * cfg[K.ORIGIN_X], cfg[K.ORIGIN_Y] + 20
        sp.callback_start = lambda s: None          # we draw; PeppySpectrum only reads the pipe
        sp.start()
        self.spec_rect = pygame.Rect(cfg[K.SPECTRUM_X], cfg[K.SPECTRUM_Y], size[0], size[1]).clip(self.full)
        self.screen.set_clip(self.spec_rect)
        if sp.components[0].content is not None:
            sp.components[0].draw()                 # the spectrum's own panel, part of the fixed picture
        self.screen.set_clip(None)
        self.sp = sp

    def plan(self):
        s = self.skin
        centre = flag(s.get("playinfo.center", "")) or flag(s.get("playinfo.text.center", ""))
        default = colour(s.get("font.color"), (220, 220, 220))
        sizes = {k: int(s.get(f"font.size.{k}", d) or d) for k, d in (("light", 30), ("regular", 35), ("bold", 40), ("digi", 40))}
        for style in ("light", "regular", "bold"):
            self.fonts[style] = load(font_file(style), sizes[style])
        self.fonts["digi"] = digit_font(sizes["digi"])
        self.centre = centre

        def text_item(key, default_colour, prefix=None):
            prefix = prefix or f"playinfo.{key}"
            pos = s.get(f"{prefix}.pos", "")
            xy = ints(pos, 2)
            if not xy:
                return
            parts = [p.strip().lower() for p in pos.split(",")]
            style = parts[2] if len(parts) > 2 and parts[2] in self.fonts else "regular"
            width = ints(s.get(f"{prefix}.maxwidth", ""), 1) or ints(s.get("playinfo.maxwidth", ""), 1)
            width = width[0] if width else (int(SCREEN_W * 0.6) if centre else max(0, SCREEN_W - xy[0] - 20))
            font = self.fonts[style]
            it = Item(pygame.Rect(xy[0], xy[1], width, font.get_linesize()).clip(self.full))
            it.font, it.colour = font, colour(s.get(f"{prefix}.color"), default_colour)
            self.items[key] = it

        for key in ("title", "artist", "album"):
            text_item(key, default)
        type_colour = colour(s.get("playinfo.type.color"), default)
        text_item("rate", type_colour, prefix="playinfo.samplerate")

        xy = ints(s.get("time.remaining.pos", ""), 2)
        if xy:
            f = self.fonts["digi"]
            it = Item(pygame.Rect(xy[0], xy[1], f.size("00:00")[0] + 6, f.get_linesize()).clip(self.full))
            it.font, it.colour = f, colour(s.get("time.remaining.color"), default)
            self.items["time"] = it

        xy, dim = ints(s.get("albumart.pos", ""), 2), ints(s.get("albumart.dimension", ""), 2)
        if xy and dim:
            self.items["art"] = Item(pygame.Rect(xy, dim).clip(self.full))
            self.art_mask = self.load_mask(s.get("albumart.mask"), dim)

        xy, dim = ints(s.get("playinfo.type.pos", ""), 2), ints(s.get("playinfo.type.dimension", ""), 2)
        self.badge = None
        if xy and dim and V.get("format_image"):
            path = V.get("format_image")
            path = path if os.path.isabs(path) else os.path.join(rpf_settings.BASE_DIR, path)
            try:
                self.badge = contain(pygame.image.load(path).convert_alpha(), *dim)
                self.items["badge"] = Item(pygame.Rect(xy, dim).clip(self.full))
            except Exception as e:
                print(f"Could not load format_image {path}: {e}", flush=True)

    def load_mask(self, filename, dim):
        """albumart.mask: a picture the size of the art; black = art shows, white = it doesn't."""
        if not filename:
            return None
        try:
            img = pygame.transform.smoothscale(pygame.image.load(os.path.join(self.dir, filename)).convert(), dim)
            return 255 - pygame.surfarray.array3d(img)[:, :, 0]
        except Exception as e:
            print(f"Could not load art mask {filename}: {e}", flush=True)
            return None

    # -- what each place should show now ------------------------------------------------

    def wanted(self, key):
        info, stopped = self.overlay.info, self.overlay.state() == "stopped"
        if key in ("title", "artist", "album"):
            return "" if stopped else (info.get(key) or "")
        if key == "rate":
            return V.get("format_text")
        if key == "time":
            p = self.overlay.position()
            if p:
                if self.remaining:
                    secs = math.ceil(p[1] - p[0])       # counts down to 00:00 as the track ends
                else:
                    secs = int(p[0])
                m, sec = divmod(max(0, secs), 60)
                return f"{m:02}:{sec:02}"
            return time.strftime("%H:%M")
        if key == "art":
            return None if stopped else self.art_key
        return "badge"

    def paint(self, key, it, want):
        """Draw item `key` showing `want` onto the fixed picture."""
        self.static.blit(self.base, it.rect.topleft, it.rect)
        if key == "art":
            if want and self.art:
                self.static.blit(self.art, it.rect.topleft)
        elif key == "badge":
            self.static.blit(self.badge, self.badge.get_rect(center=it.rect.center))
        elif want:
            surf = it.font.render(fit(it.font, want, it.rect.w) if key != "time" else want, True, it.colour)
            x = it.rect.x + (it.rect.w - surf.get_width()) // 2 if (self.centre and key != "time") else it.rect.x
            self.static.set_clip(it.rect)
            self.static.blit(surf, (x, it.rect.y))
            self.static.set_clip(None)
        if self.meter_bg:
            ox, oy = self.meter_origin
            self.meter_bg.blit(self.static, (it.rect.x - ox, it.rect.y - oy), it.rect)

    def load_art(self):
        key = self.overlay.art_key
        if key == self.art_key:
            return
        self.art_key, self.art = key, None
        it = self.items.get("art")
        if not key or not it:
            return
        try:
            img = cover(pygame.image.load(ART_FILE).convert(), it.rect.w, it.rect.h)
            if self.art_mask is not None:
                img = img.convert_alpha()
                alpha = pygame.surfarray.pixels_alpha(img)
                alpha[:, :] = self.art_mask[:alpha.shape[0], :alpha.shape[1]]
                del alpha
            self.art = img
        except Exception as e:
            print(f"Could not load artwork: {e}", flush=True)

    def refresh_items(self, force=False):
        """Bring the details up to date; returns the rectangles that changed on screen."""
        self.load_art()
        changed = []
        for key, it in self.items.items():
            want = self.wanted(key)
            if force or want != it.shown:
                it.shown = want
                self.paint(key, it, want)
                changed.append(it.rect)
        for r in changed:
            self.to_screen(r)
        return changed

    def to_screen(self, rect):
        self.screen.blit(self.static, rect.topleft, rect)
        self.over(rect)

    def over(self, rect):
        """The meter's foreground (glass, bezel) goes on top of everything."""
        if self.fgr:
            ox, oy = self.meter_origin
            self.screen.blit(self.fgr, rect.topleft, rect.move(-ox, -oy))

    def draw_spectrum(self):
        self.screen.set_clip(self.spec_rect)
        self.screen.blit(self.static, self.spec_rect.topleft, self.spec_rect)
        for comp in self.sp.components[1:]:
            comp.draw()
        self.screen.set_clip(None)
        self.over(self.spec_rect)
        return self.spec_rect

    def redraw_all(self):
        self.refresh_items(force=True)
        if self.meter_on:
            self.pm.meter.start()               # skin picture, meter face (with details), needles
            for it in self.items.values():
                self.to_screen(it.rect)
        else:
            self.screen.blit(self.static, (0, 0))
        if self.sp:
            self.draw_spectrum()
        pygame.display.update(self.full)

    # -- main loop ----------------------------------------------------------------------

    def run(self):
        from configfileparser import FRAME_RATE
        fps = self.pm.util.meter_config[FRAME_RATE]
        spec_every = max(1, round(fps / max(5, V.getint("display_fps"))))
        clock = Clock()
        pygame.event.clear()
        self.overlay.tick()
        self.redraw_all()
        paused_view = False
        frames = 0
        while True:
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    self.pm.exit()

            self.overlay.tick()
            if self.overlay.state() == "paused":
                if not paused_view or self.overlay.dirty:
                    self.overlay.draw_paused()
                    pygame.display.update(self.full)
                    paused_view = True
            elif paused_view:
                self.redraw_all()
                paused_view = False
            else:
                areas = self.refresh_items()
                if self.meter_on:
                    areas += [a for a in (self.pm.meter.run() or []) if a]
                if self.sp and frames % spec_every == 0:
                    areas.append(self.draw_spectrum())
                if areas:
                    pygame.display.update(areas)
                if self.meter_on:
                    self.pm.refresh()

            frames += 1
            if self.snapshot and frames >= self.snapshot[1] * fps:
                pygame.image.save(self.screen, self.snapshot[0])
                print(f"Snapshot saved to {self.snapshot[0]}", flush=True)
                os._exit(0)
            clock.tick(fps)


def main():
    snapshot = None
    if len(sys.argv) == 4 and sys.argv[1] == "--snapshot":
        snapshot = (sys.argv[2], float(sys.argv[3]))
    folder, name = vsd.current_skin()
    pack = vis_settings.hybrid_pack(folder)
    if not pack:
        vsd.die(f"'{folder}' is not a meter + spectrum skin folder in {vis_settings.HYBRID_DIR}")
    read_skin(pack, folder, name)                   # stops here with a clear message if the name is wrong

    write_meter_config(folder, name, os.path.join(pack, "templates"))
    os.chdir(METER_RUN_DIR)
    from peppymeter import Peppymeter
    from configfileparser import SCREEN_INFO, WIDTH, HEIGHT, DATA_SOURCE, TYPE
    from datasource import SOURCE_PIPE
    pm = Peppymeter(standalone=True)
    pm.util.meter_config[SCREEN_INFO][WIDTH], pm.util.meter_config[SCREEN_INFO][HEIGHT] = SCREEN_W, SCREEN_H
    if pm.util.meter_config[DATA_SOURCE][TYPE] != SOURCE_PIPE:
        pm.data_source.start_data_source()
    pm.init_display()
    Hybrid(pm, pack, folder, name, snapshot).run()


if __name__ == "__main__":
    main()
