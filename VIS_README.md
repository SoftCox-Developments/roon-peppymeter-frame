# Visualiser extension for Roon PeppyMeter Frame

Adds a `vis` command that shows a spectrum analyser on the display instead of the
meters, with the same now-playing strip and paused screen. Any `meter` switch (or
`vis off`) brings the meters back.

## What is what

Everything belonging to the extension is named `vis...`. The meter programs are not
edited.

| File | What it is |
|------|-----------|
| `vis` | the command (installed to `/usr/local/bin/vis`) |
| `vis_audio_hub.py` | replaces `audio_bridge.py` while the extension is installed: same meter feed, plus spectrum data on request |
| `vis_spectrum_display.py` | runs unmodified PeppySpectrum with the strip from `frame_display.py` |
| `vis_make_skins.py` | writes the extension's own spectrum skins into `vis_skins/` |
| `vis_settings.py` | paths and the optional `[vis]` settings |
| `vis_install.sh`, `vis_uninstall.sh` | add / remove the extension |
| `VIS_README.md` | this file |

Created on the Pi by the installer: `PeppySpectrum/` (cloned), `vis_skins/`, `vis_run/`,
`vis_current.txt`, `vis_strip.txt`, `vis_hidden.txt`.

System changes made by `vis_install.sh` (all undone by `vis_uninstall.sh`):

- `/etc/systemd/system/rpf-vis.service` - the visualiser display. Not enabled at boot;
  it and `rpf-display` stop each other, because only one program can drive the screen.
- `/etc/systemd/system/rpf-audio.service.d/vis.conf` - makes `rpf-audio` run
  `vis_audio_hub.py` instead of `audio_bridge.py`.
- `/etc/sudoers.d/roon-peppymeter-frame-vis` - lets `vis` restart `rpf-vis` without a password.
- `/usr/local/bin/vis`

## Install

Needs a working Roon PeppyMeter Frame (installed with `install.sh`). From the install
folder:

    bash vis_install.sh

## Use

    vis              list the visualisers
    vis 8            show number 8
    vis next         next one (also prev, random)
    vis strip dim    strip for the current visualiser: clear, dim, black or off
    vis hide 3       take number 3 out of the list (vis hide = the selected one)
    vis unhide       list the hidden ones; vis unhide 2 puts one back
    vis off          back to the meters (any 'meter' switch does the same)
    vis --help

Skins in the `1920x720` folder leave room for the strip underneath, so the bars and the
now-playing details are both in full view.

Skins in the `1920x1080` folder fill the whole screen with bars and have no strip. They
start hidden: `vis unhide` lists them. Turning the strip on over one covers the bottom
of its bars, so for bars with a strip use the `1920x720` version of the same look.

## Settings

Optional. Add a `[vis]` section to `settings.conf`; the defaults are:

    [vis]
    spectrum_fps = 60          # spectrum frames sent per second
    analysis_fps = 30          # times per second the audio is re-analysed
    display_fps = 30           # screen updates per second
    fft_size = 4096            # samples analysed per frame
    freq_low = 40              # Hz, first bar
    freq_high = 16000          # Hz, last bar
    db_floor = -60             # level drawn as an empty bar (dB below full scale)
    db_top = -12               # level drawn as a full bar
    tilt_db_per_octave = 3     # lifts treble, lowers bass, around 1 kHz
    gain_db = 0                # raise or lower all bars
    attack = 0.7               # 0-1, how fast bars rise
    fall_time = 0.5            # seconds for a full bar to fall

After a change: `sudo systemctl restart rpf-audio` (and `vis N` again for display_fps).
If the bars sit too low or hit the top on your music, change `gain_db` first.

## Your own skins

`vis_skins/<WIDTH>x<HEIGHT>-anything/spectrum.txt` in PeppySpectrum's format, one
`[section]` per skin. Add `rpf.bars = N` for the number of bars; without it the display
fits as many as the skin's bar width allows. `vis_make_skins.py` rewrites only its own
two folders.

## Known limits

- After a reboot the meters come back; run `vis N` again.
- `vis` turns the meter slideshow off (it would keep switching back to the meters).
- No slideshow for visualisers yet.

## Credits

PeppySpectrum by peppy.player (https://github.com/project-owner/PeppySpectrum),
GPL-3.0-or-later, used unmodified and downloaded at install. The spectrum data format
is the one produced by its companion peppyalsa.
