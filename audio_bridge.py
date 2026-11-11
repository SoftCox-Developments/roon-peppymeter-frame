#!/usr/bin/env python3
# Roon PeppyMeter Frame - audio bridge
#
# Copyright (C) 2026 Andrew Cox (SoftCox Developments)
# SPDX-License-Identifier: GPL-3.0-or-later
#
# This program is free software: you can redistribute it and/or modify it under the terms of
# the GNU General Public License as published by the Free Software Foundation, either
# version 3 of the License, or (at your option) any later version. See LICENSE.
"""Capture line-level audio and feed peak levels to PeppyMeter through a named pipe.

Each record is two little-endian uint16 values (left peak, right peak, 0..32767),
which matches PeppyMeter's pipe data source with volume.max.in.pipe = 32767.

Rate matters. PeppyMeter's pipe reader reads one 4-byte record, sleeps
polling.interval / 10, and repeats until the pipe is empty. Send much faster
than it can drain and that loop never ends (frozen needles); send slower than
it polls and it reads an empty pipe as silence (dipping needles). The default
120 records/s sits safely between the two at PeppyMeter's 60 polls/s.
"""
import errno
import logging
import os
import stat
import struct
import sys
import time

import alsaaudio
import numpy as np

import rpf_settings

S = rpf_settings.load()
DEVICE = S.get("audio", "device")
RATE = S.getint("audio", "rate")
UPDATES_PER_SEC = S.getint("audio", "updates_per_sec")
CHANNELS = 2
PIPE = rpf_settings.PIPE
FRAMES_PER_UPDATE = max(1, RATE // UPDATES_PER_SEC)

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
log = logging.getLogger("audio")


def ensure_fifo():
    """Create the named pipe if it is missing or is not a pipe."""
    if os.path.exists(PIPE):
        if stat.S_ISFIFO(os.stat(PIPE).st_mode):
            return
        os.remove(PIPE)
    os.mkfifo(PIPE, 0o666)


def open_capture():
    """Open the capture device in blocking mode, so reads sleep until audio arrives."""
    return alsaaudio.PCM(
        type=alsaaudio.PCM_CAPTURE,
        mode=alsaaudio.PCM_NORMAL,
        device=DEVICE,
        rate=RATE,
        channels=CHANNELS,
        format=alsaaudio.PCM_FORMAT_S16_LE,
        periodsize=max(32, FRAMES_PER_UPDATE // 2),
    )


def try_open_pipe():
    """Open the pipe for writing without blocking. None if PeppyMeter isn't reading yet."""
    try:
        return os.open(PIPE, os.O_WRONLY | os.O_NONBLOCK)
    except OSError as e:
        if e.errno == errno.ENXIO:
            return None
        raise


def main():
    if not DEVICE:
        log.error("No capture device set. Put e.g. 'device = plughw:CARD=CODEC,DEV=0' under [audio] "
                  "in %s (see 'arecord -l'), then: sudo systemctl restart rpf-audio", rpf_settings.SETTINGS_FILE)
        time.sleep(30)
        sys.exit(1)

    ensure_fifo()
    pcm = open_capture()
    log.info("Capturing from %s at %d Hz; sending %d updates/s to %s", DEVICE, RATE, UPDATES_PER_SEC, PIPE)

    fd = None
    last_attempt = 0.0
    peak_l = peak_r = 0
    frames = 0

    while True:
        length, data = pcm.read()
        if length < 0:
            log.warning("Capture overrun (code %d); continuing", length)
            continue
        if length == 0:
            continue

        samples = np.frombuffer(data, dtype=np.int16).astype(np.int32)   # int32: abs(-32768) fits
        peak_l = max(peak_l, int(np.abs(samples[0::2]).max()))
        peak_r = max(peak_r, int(np.abs(samples[1::2]).max()))
        frames += length
        if frames < FRAMES_PER_UPDATE:
            continue

        record = struct.pack("<HH", min(peak_l, 32767), min(peak_r, 32767))
        peak_l = peak_r = 0
        frames = 0

        if fd is None:
            now = time.monotonic()
            if now - last_attempt < 1.0:
                continue
            last_attempt = now
            fd = try_open_pipe()
            if fd is None:
                continue
            log.info("PeppyMeter connected to pipe")

        try:
            os.write(fd, record)
        except BlockingIOError:
            pass    # pipe full: drop this reading rather than fall behind
        except BrokenPipeError:
            log.info("PeppyMeter disconnected; waiting for it to return")
            os.close(fd)
            fd = None


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        pass
