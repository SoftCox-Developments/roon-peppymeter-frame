#!/usr/bin/env python3
# Roon PeppyMeter Frame - VISUALISER EXTENSION - projectM TRIAL
#
# Copyright (C) 2026 Andrew Cox (SoftCox Developments)
# SPDX-License-Identifier: GPL-3.0-or-later
#
# This program is free software: you can redistribute it and/or modify it under the terms of
# the GNU General Public License as published by the Free Software Foundation, either
# version 3 of the License, or (at your option) any later version. See LICENSE.
#
# Uses projectM (https://github.com/projectM-visualizer/projectm, LGPL-2.1) as a shared
# library, built by vis_projectm_trial_build.sh.
"""Trial: how well does projectM (MilkDrop presets) run on this computer?

Shows a sample of presets, each for a few seconds, driven by the live audio, and measures
the frame rate of each. Results go to the terminal and to vis_projectm_trial.log.

By default the picture fills the top two thirds of the screen (1920x720 on a 1080p screen),
leaving the space where the now-playing strip will go; --full uses the whole screen. The
picture is rendered at --size and scaled up, which is how slower computers keep up.

Run it through vis_projectm_trial.sh, which frees the screen first and restores it after.
"""
import argparse
import ctypes as C
import glob
import os
import random
import statistics
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import rpf_settings
import vis_settings

import numpy as np
import pygame

GL_TEXTURE_2D, GL_RGBA, GL_RGBA8, GL_UNSIGNED_BYTE = 0x0DE1, 0x1908, 0x8058, 0x1401
GL_FRAMEBUFFER, GL_READ_FRAMEBUFFER, GL_DRAW_FRAMEBUFFER = 0x8D40, 0x8CA8, 0x8CA9
GL_COLOR_ATTACHMENT0, GL_FRAMEBUFFER_COMPLETE = 0x8CE0, 0x8CD5
GL_COLOR_BUFFER_BIT, GL_LINEAR, GL_TEXTURE_MIN_FILTER, GL_TEXTURE_MAG_FILTER = 0x4000, 0x2601, 0x2801, 0x2800
GL_VERSION, GL_RENDERER = 0x1F02, 0x1F01


def size(text):
    w, _, h = text.lower().partition("x")
    return int(w), int(h)


def args():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--size", type=size, default=None, metavar="WxH",
                   help="size projectM renders at (default 1280x480, or 1280x720 with --full)")
    p.add_argument("--full", action="store_true", help="fill the whole screen instead of the top two thirds")
    p.add_argument("--count", type=int, default=40, help="number of presets to try (default 40)")
    p.add_argument("--seconds", type=float, default=15, help="seconds per preset (default 15)")
    p.add_argument("--folder", default="", help="only presets whose path contains this, e.g. Fractal")
    p.add_argument("--seed", type=int, default=1, help="which random sample (same seed = same presets; default 1)")
    p.add_argument("--mesh", type=size, default=(48, 32), metavar="WxH", help="projectM mesh size (default 48x32)")
    p.add_argument("--lib", default=os.environ.get("RPF_PROJECTM_LIB", os.path.join(vis_settings.PROJECTM_DIR, "inst", "lib")))
    p.add_argument("--presets", default=os.path.join(vis_settings.PROJECTM_DIR, "presets"))
    p.add_argument("--snapshot", default="", help=argparse.SUPPRESS)       # testing: save a picture of each preset here
    return p.parse_args()


def load_projectm(libdir):
    path = os.path.join(libdir, "libprojectM-4.so.4")
    if not os.path.isfile(path):
        sys.exit(f"{path} not found. Run: bash vis_projectm_trial_build.sh")
    pm = C.CDLL(path)
    pm.projectm_create.restype = C.c_void_p
    pm.projectm_get_version_string.restype = C.c_char_p
    for name, a in (("projectm_set_window_size", [C.c_void_p, C.c_size_t, C.c_size_t]),
                    ("projectm_set_mesh_size", [C.c_void_p, C.c_size_t, C.c_size_t]),
                    ("projectm_set_fps", [C.c_void_p, C.c_int32]),
                    ("projectm_set_preset_locked", [C.c_void_p, C.c_bool]),
                    ("projectm_set_aspect_correction", [C.c_void_p, C.c_bool]),
                    ("projectm_set_texture_search_paths", [C.c_void_p, C.POINTER(C.c_char_p), C.c_size_t]),
                    ("projectm_load_preset_file", [C.c_void_p, C.c_char_p, C.c_bool]),
                    ("projectm_pcm_add_int16", [C.c_void_p, C.c_void_p, C.c_uint, C.c_int]),
                    ("projectm_opengl_render_frame_fbo", [C.c_void_p, C.c_uint32]),
                    ("projectm_destroy", [C.c_void_p])):
        f = getattr(pm, name)
        f.argtypes, f.restype = a, None
    return pm


class Audio:
    """Reads the audio hub's raw feed without ever waiting for it."""

    def __init__(self):
        self.fd = None
        self.rest = b""
        self.bytes = 0
        try:
            self.fd = os.open(vis_settings.PCM_PIPE, os.O_RDONLY | os.O_NONBLOCK)
        except OSError:
            print(f"NOTE: no audio feed at {vis_settings.PCM_PIPE} - the presets will run without sound. "
                  "Restart the audio hub: sudo systemctl restart rpf-audio", flush=True)

    def feed(self, pm, handle):
        if self.fd is None:
            return
        try:
            data = self.rest + os.read(self.fd, 65536)
        except BlockingIOError:
            return
        except OSError:
            return
        usable = len(data) - len(data) % 4
        self.rest = data[usable:]
        if usable:
            self.bytes += usable
            buf = np.frombuffer(data[:usable], dtype=np.int16)
            pm.projectm_pcm_add_int16(handle, buf.ctypes.data, usable // 4, 2)


def main():
    a = args()
    presets = sorted(p for p in glob.glob(os.path.join(a.presets, "**", "*.milk"), recursive=True)
                     if a.folder.lower() in p.lower() and "! Transition" not in p)
    if not presets:
        sys.exit(f"No presets found in {a.presets}. Run: bash vis_projectm_trial_build.sh")
    random.Random(a.seed).shuffle(presets)
    presets = presets[:a.count]

    S = rpf_settings.load()
    sw, sh = S.getint("display", "width"), S.getint("display", "height")
    pygame.display.init()
    pygame.display.gl_set_attribute(pygame.GL_CONTEXT_PROFILE_MASK, pygame.GL_CONTEXT_PROFILE_ES)
    pygame.display.gl_set_attribute(pygame.GL_CONTEXT_MAJOR_VERSION, 3)
    pygame.display.gl_set_attribute(pygame.GL_CONTEXT_MINOR_VERSION, 0)
    pygame.display.gl_set_attribute(pygame.GL_DOUBLEBUFFER, 1)
    flags = pygame.OPENGL | pygame.DOUBLEBUF | (0 if pygame.display.get_driver() == "offscreen" else pygame.FULLSCREEN)
    pygame.display.set_mode((sw, sh), flags, vsync=1)
    pygame.mouse.set_visible(False)

    gl = C.CDLL("libGLESv2.so.2")
    gl.glGetString.restype = C.c_char_p
    area_h = sh if a.full else sh * 2 // 3
    rw, rh = a.size or ((1280, 720) if a.full else (1280, 480))
    tex, fbo = C.c_uint(), C.c_uint()
    gl.glGenTextures(1, C.byref(tex))
    gl.glBindTexture(GL_TEXTURE_2D, tex)
    gl.glTexImage2D(GL_TEXTURE_2D, 0, GL_RGBA8, rw, rh, 0, GL_RGBA, GL_UNSIGNED_BYTE, None)
    gl.glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_LINEAR)
    gl.glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_LINEAR)
    gl.glGenFramebuffers(1, C.byref(fbo))
    gl.glBindFramebuffer(GL_FRAMEBUFFER, fbo)
    gl.glFramebufferTexture2D(GL_FRAMEBUFFER, GL_COLOR_ATTACHMENT0, GL_TEXTURE_2D, tex, 0)
    if gl.glCheckFramebufferStatus(GL_FRAMEBUFFER) != GL_FRAMEBUFFER_COMPLETE:
        sys.exit("Could not create the off-screen picture (framebuffer incomplete)")

    pm = load_projectm(a.lib)
    h = pm.projectm_create()
    if not h:
        sys.exit("projectM could not start in this OpenGL context")
    pm.projectm_set_window_size(h, rw, rh)
    pm.projectm_set_mesh_size(h, *a.mesh)
    pm.projectm_set_fps(h, 60)
    pm.projectm_set_preset_locked(h, True)          # we change presets ourselves
    pm.projectm_set_aspect_correction(h, True)
    tdir = os.path.join(vis_settings.PROJECTM_DIR, "textures", "textures")
    if os.path.isdir(tdir):
        paths = (C.c_char_p * 1)(tdir.encode())
        pm.projectm_set_texture_search_paths(h, paths, 1)

    log_path = os.path.join(HERE, "vis_projectm_trial.log")
    logf = open(log_path, "a", encoding="utf-8")

    def say(text):
        print(text, flush=True)
        logf.write(text + "\n")
        logf.flush()

    say(f"\n=== projectM trial {time.strftime('%Y-%m-%d %H:%M')} ===")
    say(f"projectM {pm.projectm_get_version_string().decode()} | {gl.glGetString(GL_VERSION).decode()} | "
        f"{gl.glGetString(GL_RENDERER).decode()} | video driver {pygame.display.get_driver()}")
    say(f"screen {sw}x{sh}, picture {sw}x{area_h} ({'full screen' if a.full else 'strip space left free'}), "
        f"rendered at {rw}x{rh}, mesh {a.mesh[0]}x{a.mesh[1]}; {len(presets)} presets x {a.seconds:g} s, seed {a.seed}"
        + (f", folder '{a.folder}'" if a.folder else ""))
    say("  fps  worst-ms  load-ms  preset")

    audio = Audio()
    results = []
    clock_start = time.monotonic()
    try:
        for i, preset in enumerate(presets):
            t0 = time.perf_counter()
            pm.projectm_load_preset_file(h, preset.encode(), False)
            frames, worst, first = 0, 0.0, None
            start = last = time.perf_counter()
            while last - start < a.seconds:
                for event in pygame.event.get():
                    if event.type == pygame.QUIT:
                        raise KeyboardInterrupt
                audio.feed(pm, h)
                pm.projectm_opengl_render_frame_fbo(h, fbo.value)
                gl.glBindFramebuffer(GL_READ_FRAMEBUFFER, fbo)
                gl.glBindFramebuffer(GL_DRAW_FRAMEBUFFER, 0)
                gl.glBlitFramebuffer(0, 0, rw, rh, 0, sh - area_h, sw, sh, GL_COLOR_BUFFER_BIT, GL_LINEAR)
                pygame.display.flip()
                now = time.perf_counter()
                if first is None:
                    first = (now - t0) * 1000          # loading + first frame (shader compilation)
                    start = now
                else:
                    worst = max(worst, (now - last) * 1000)
                    frames += 1
                last = now
            fps = frames / max(1e-6, last - start)
            name = os.path.relpath(preset, a.presets)
            results.append((fps, worst, first, name))
            say(f"{fps:5.1f}  {worst:8.0f}  {first:7.0f}  {name[:110]}")
            if a.snapshot:
                buf = (C.c_ubyte * (rw * rh * 4))()
                gl.glBindFramebuffer(GL_FRAMEBUFFER, fbo)
                gl.glReadPixels(0, 0, rw, rh, GL_RGBA, GL_UNSIGNED_BYTE, buf)
                surf = pygame.image.frombuffer(bytes(buf), (rw, rh), "RGBA")
                pygame.image.save(pygame.transform.flip(surf, False, True), os.path.join(a.snapshot, f"trial{i:02d}.png"))
    except KeyboardInterrupt:
        say("(stopped early)")

    if results:
        fpss = sorted(r[0] for r in results)
        n = len(fpss)
        say(f"--- {n} presets in {time.monotonic() - clock_start:.0f} s: median {statistics.median(fpss):.0f} fps, "
            f"slowest {fpss[0]:.0f}, fastest {fpss[-1]:.0f}")
        for limit in (50, 30, 20):
            say(f"    at least {limit} fps: {sum(f >= limit for f in fpss)} of {n} ({100 * sum(f >= limit for f in fpss) // n}%)")
        say(f"    median load time {statistics.median(r[2] for r in results):.0f} ms, longest {max(r[2] for r in results):.0f} ms")
        secs = sum(r[0] * a.seconds for r in results) and (time.monotonic() - clock_start)
        say(f"    audio received: {audio.bytes / 176400:.0f} s of {secs:.0f} s" if audio.fd is not None else "    audio: none")
        say(f"Saved to {log_path}")
    pm.projectm_destroy(h)
    pygame.quit()


if __name__ == "__main__":
    main()
