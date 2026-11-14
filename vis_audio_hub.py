#!/usr/bin/env python3
# Roon PeppyMeter Frame - VISUALISER EXTENSION - audio hub
#
# Copyright (C) 2026 Andrew Cox (SoftCox Developments)
# SPDX-License-Identifier: GPL-3.0-or-later
#
# This program is free software: you can redistribute it and/or modify it under the terms of
# the GNU General Public License as published by the Free Software Foundation, either
# version 3 of the License, or (at your option) any later version. See LICENSE.
"""Capture line-level audio once and feed every display that wants it.

Replaces audio_bridge.py while the visualiser extension is installed (a systemd drop-in
points rpf-audio at this file; audio_bridge.py itself is untouched). It is still the only
program that opens the capture device. Feeds:

  peaks     two little-endian uint16 (left, right peak) to PeppyMeter's pipe - exactly what
            audio_bridge.py sends, at the same rate, with the same rules (see that file).
  spectrum  frames of N little-endian uint32 values 0..100, one per frequency bar, in the
            format PeppySpectrum expects from peppyalsa. Sent to every FIFO named
            /tmp/rpf_spectrum_<N> that has a reader; nothing is computed when none has.

Spectrum maths: mono mix, Hann window, FFT, power summed into N log-spaced bands between
freq_low and freq_high, expressed in dB relative to a full-scale sine and normalised to
third-octave bandwidth (so levels do not depend on the number of bars), tilted around
1 kHz, mapped db_floor..db_top to 0..100, then smoothed (fast rise, timed fall).
"""
import errno
import glob
import logging
import os
import stat
import struct
import sys
import time

import numpy as np

import rpf_settings
import vis_settings

S = rpf_settings.load()
V = vis_settings.load()
DEVICE = S.get("audio", "device")
RATE = S.getint("audio", "rate")
UPDATES_PER_SEC = S.getint("audio", "updates_per_sec")
CHANNELS = 2
PIPE = rpf_settings.PIPE
FRAMES_PER_UPDATE = max(1, RATE // UPDATES_PER_SEC)

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
log = logging.getLogger("audio")


def open_writer(path):
    """Open a FIFO for writing without blocking. None if nothing is reading it."""
    try:
        return os.open(path, os.O_WRONLY | os.O_NONBLOCK)
    except OSError as e:
        if e.errno in (errno.ENXIO, errno.ENOENT):
            return None
        raise


class PeakFeed:
    """Peak levels for PeppyMeter - same behaviour as audio_bridge.py."""

    def __init__(self):
        self.fd = None
        self.last_attempt = 0.0
        self.peak_l = self.peak_r = 0
        self.frames = 0
        if os.path.exists(PIPE) and not stat.S_ISFIFO(os.stat(PIPE).st_mode):
            os.remove(PIPE)
        if not os.path.exists(PIPE):
            os.mkfifo(PIPE, 0o666)

    def add(self, samples, length):
        self.peak_l = max(self.peak_l, int(np.abs(samples[0::2]).max()))
        self.peak_r = max(self.peak_r, int(np.abs(samples[1::2]).max()))
        self.frames += length
        if self.frames < FRAMES_PER_UPDATE:
            return
        record = struct.pack("<HH", min(self.peak_l, 32767), min(self.peak_r, 32767))
        self.peak_l = self.peak_r = 0
        self.frames = 0

        if self.fd is None:
            now = time.monotonic()
            if now - self.last_attempt < 1.0:
                return
            self.last_attempt = now
            self.fd = open_writer(PIPE)
            if self.fd is None:
                return
            log.info("PeppyMeter connected to pipe")
        try:
            os.write(self.fd, record)
        except BlockingIOError:
            pass    # pipe full: drop this reading rather than fall behind
        except BrokenPipeError:
            log.info("PeppyMeter disconnected; waiting for it to return")
            os.close(self.fd)
            self.fd = None


class Bands:
    """Turns one block of mono samples into `bars` levels 0..100 (no smoothing)."""

    def __init__(self, bars, rate, v=V):
        self.bars = bars
        self.n = max(256, v.getint("fft_size"))
        self.window = np.hanning(self.n).astype(np.float32)
        # Scale so that the band powers of a full-scale sine add up to 1.0 (0 dB)
        self.scale = 2.0 / (self.n * float(np.sum(self.window ** 2))) / (32768.0 ** 2 / 2.0)
        df = rate / self.n
        self.bin_edges = (np.arange(self.n // 2 + 2) - 0.5) * df          # frequency edges of FFT bins
        lo = max(df, v.getfloat("freq_low"))
        hi = min(rate / 2.0, max(lo * 2, v.getfloat("freq_high")))
        self.edges = lo * (hi / lo) ** (np.arange(bars + 1) / bars)       # log-spaced band edges
        centres = np.sqrt(self.edges[:-1] * self.edges[1:])
        bands_per_octave = bars / np.log2(hi / lo)
        self.offset = (10 * np.log10(bands_per_octave / 3.0)              # as if third-octave bands
                       + v.getfloat("tilt_db_per_octave") * np.log2(centres / 1000.0)
                       + v.getfloat("gain_db"))
        self.floor = v.getfloat("db_floor")
        self.span = max(1.0, v.getfloat("db_top") - self.floor)

    def levels(self, mono):
        power = np.abs(np.fft.rfft(mono * self.window)) ** 2 * self.scale
        power[0] = 0.0                                                    # ignore DC
        cum = np.concatenate(([0.0], np.cumsum(power)))
        at = np.interp(self.edges, self.bin_edges, cum)                   # power below each band edge
        db = 10 * np.log10(np.maximum(at[1:] - at[:-1], 1e-12)) + self.offset
        return np.clip((db - self.floor) / self.span * 100.0, 0.0, 100.0)


class SpectrumFeed:
    """Spectrum frames for every /tmp/rpf_spectrum_<bars> FIFO that has a reader."""

    def __init__(self, rate=RATE, v=V):
        self.rate = rate
        self.n = max(256, v.getint("fft_size"))
        self.fps = max(1.0, v.getfloat("spectrum_fps"))
        self.step = rate / self.fps
        self.attack = min(1.0, max(0.05, v.getfloat("attack")))
        self.fall = 100.0 / (max(0.05, v.getfloat("fall_time")) * self.fps)   # units per frame
        self.buf = np.zeros(self.n, dtype=np.float32)
        self.pending = 0.0
        self.readers = {}       # path -> [fd, Bands, smoothed levels]
        self.next_scan = 0.0

    def scan(self):
        for path in glob.glob(vis_settings.SPECTRUM_PIPE_PREFIX + "*"):
            if path in self.readers:
                continue
            try:
                bars = int(path[len(vis_settings.SPECTRUM_PIPE_PREFIX):])
                is_fifo = stat.S_ISFIFO(os.stat(path).st_mode)
            except (ValueError, OSError):
                continue
            if not is_fifo or not 1 <= bars <= vis_settings.MAX_BARS:
                continue
            fd = open_writer(path)
            if fd is not None:
                self.readers[path] = [fd, Bands(bars, self.rate), np.zeros(bars)]
                log.info("Spectrum display connected (%d bars)", bars)

    def add(self, samples, length):
        now = time.monotonic()
        if now >= self.next_scan:
            self.next_scan = now + 1.0
            self.scan()
        if not self.readers:
            return
        mono = (samples[0::2] + samples[1::2]) * 0.5
        if length >= self.n:
            self.buf[:] = mono[-self.n:]
        else:
            self.buf[:-length] = self.buf[length:]
            self.buf[-length:] = mono
        self.pending += length
        if self.pending < self.step:
            return
        self.pending = min(self.pending - self.step, self.step)

        for path, r in list(self.readers.items()):
            fd, bands, smooth = r
            new = bands.levels(self.buf)
            rising = new > smooth
            smooth[rising] += (new[rising] - smooth[rising]) * self.attack
            smooth[~rising] = np.maximum(new[~rising], smooth[~rising] - self.fall)
            frame = smooth.astype("<u4").tobytes()
            try:
                os.write(fd, frame)                 # one write per frame: the reader needs whole frames
            except BlockingIOError:
                pass
            except BrokenPipeError:
                log.info("Spectrum display disconnected (%d bars)", bands.bars)
                os.close(fd)
                del self.readers[path]


def open_capture():
    """Open the capture device in blocking mode, so reads sleep until audio arrives."""
    import alsaaudio
    return alsaaudio.PCM(
        type=alsaaudio.PCM_CAPTURE,
        mode=alsaaudio.PCM_NORMAL,
        device=DEVICE,
        rate=RATE,
        channels=CHANNELS,
        format=alsaaudio.PCM_FORMAT_S16_LE,
        periodsize=max(32, FRAMES_PER_UPDATE // 2),
    )


def main():
    if not DEVICE:
        log.error("No capture device set. Put e.g. 'device = plughw:CARD=CODEC,DEV=0' under [audio] "
                  "in %s (see 'arecord -l'), then: sudo systemctl restart rpf-audio", rpf_settings.SETTINGS_FILE)
        time.sleep(30)
        sys.exit(1)

    peaks = PeakFeed()
    spectrum = SpectrumFeed()
    pcm = open_capture()
    log.info("Audio hub (visualiser extension): capturing from %s at %d Hz; %d peak updates/s to %s; "
             "spectrum %d frames/s on request", DEVICE, RATE, UPDATES_PER_SEC, PIPE, spectrum.fps)

    while True:
        length, data = pcm.read()
        if length < 0:
            log.warning("Capture overrun (code %d); continuing", length)
            continue
        if length == 0:
            continue
        samples = np.frombuffer(data, dtype=np.int16).astype(np.int32)   # int32: abs(-32768) fits
        peaks.add(samples, length)
        spectrum.add(samples, length)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        pass
