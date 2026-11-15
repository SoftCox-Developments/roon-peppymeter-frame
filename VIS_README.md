# Visualiser extension for Roon PeppyMeter Frame

Adds a `vis` command that shows a spectrum analyser on the display instead of the
meters, with the same now-playing strip and paused screen. Any `meter` switch (or
`vis off`) brings the meters back.

Two kinds of visualiser are listed by `vis`:

- **Spectrum bars** (folders ending in `-rpf-spectrum`): bars above the now-playing strip.
- **Meter + spectrum designs** by Gelo5 (names with `S+M` or `Spectrum`): needles and
  bars together in one design, with the cover art, title, artist, album and time placed
  by the design itself. See [Meter + spectrum designs](#meter--spectrum-designs).

## What is what

Everything belonging to the extension is named `vis...`. The meter programs are not
edited.

| File | What it is |
|------|-----------|
| `vis` | the command (installed to `/usr/local/bin/vis`) |
| `vis_audio_hub.py` | replaces `audio_bridge.py` while the extension is installed: same meter feed, plus spectrum data on request |
| `vis_spectrum_display.py` | runs unmodified PeppySpectrum with the strip from `frame_display.py` |
| `vis_hybrid_display.py` | runs the meter + spectrum designs: unmodified PeppyMeter and PeppySpectrum together |
| `vis_make_skins.py` | writes the extension's own spectrum skins into `vis_skins/` |
| `vis_settings.py` | paths and the optional `[vis]` settings |
| `vis_install.sh`, `vis_uninstall.sh` | add / remove the extension |
| `VIS_README.md` | this file |

Created on the Pi by the installer: `PeppySpectrum/` (cloned), `vis_skins/`, `vis_hybrid/`
and `vis_fonts/` (downloaded), `vis_run/`,
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

## Meter + spectrum designs

Twenty full-screen designs by Gelo5, made for the PeppyMeter screensaver plugin for
Volumio, in which a spectrum analyser sits beside or instead of the needles. The
installer downloads them (about 30 MB) from the community template collection; they are
not part of this project.

They don't use the now-playing strip. Each design has its own places for the cover art,
title, artist, album and a digital time display, plus two small boxes that on Volumio
show the file format and resolution. Roon doesn't pass those on, so here:

| Box | Shows |
|-----|-------|
| Time | elapsed time for tracks; the time of day (24 hour) for radio and anything else without a length |
| Format badge | a picture of your choice: `format_image` in `settings.conf` |
| Resolution | a text of your choice: `format_text` in `settings.conf`, for example what your DAC is being sent |

Both boxes stay empty until you set them:

    [vis]
    format_image = my_badge.png
    format_text = DSD 1024

`format_image` is a PNG or JPEG, either a full path or a file name in the install
folder. It is scaled to fit the design's badge box (between about 55 and 130 pixels
square), so a square picture of 256 pixels or so with a transparent background works
well. Then run `vis N` again.

Paused shows the same large cover art as the meters do. `vis strip` does not apply to
these designs, and `meter shift` has no effect on them.

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
    format_image =             # meter + spectrum designs: picture for the format badge box
    format_text =              # meter + spectrum designs: text for the resolution box

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

The meter + spectrum designs are by Gelo5, from the community template collection kept
by foonerd (https://github.com/foonerd/glass_templates). The digital time display uses
the DSEG font by keshikan (SIL Open Font License). Both are downloaded at install.

PeppySpectrum by peppy.player (https://github.com/project-owner/PeppySpectrum),
GPL-3.0-or-later, used unmodified and downloaded at install. The spectrum data format
is the one produced by its companion peppyalsa.
