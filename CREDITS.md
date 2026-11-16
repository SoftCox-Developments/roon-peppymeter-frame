# Credits

Roon PeppyMeter Frame is a small layer of glue. The hard parts were done by these people and projects.

## PeppyMeter

The meters themselves. [PeppyMeter](https://github.com/project-owner/PeppyMeter) is a software VU meter written in Python by **peppy.player** (GitHub: project-owner), released under the GNU General Public License v3 or later.

This project uses PeppyMeter unmodified. `install.sh` downloads it from its own repository; `frame_display.py` builds on its `Peppymeter` class and replaces only the display loop to add the now-playing overlay. Because it builds on PeppyMeter, this project is released under the same licence.

## PeppySpectrum

The spectrum analyser behind the `vis` command. [PeppySpectrum](https://github.com/project-owner/PeppySpectrum) is PeppyMeter's sibling, also written in Python by **peppy.player** and released under the GNU General Public License v3 or later.

It is used unmodified too. `vis_install.sh` downloads it from its own repository; `vis_spectrum_display.py` builds on its `Spectrum` class and does the drawing itself, so the now-playing strip can share the screen. The spectrum data is sent in the format of its companion, [peppyalsa](https://github.com/project-owner/peppyalsa).

The spectrum skins that come with the visualiser extension are this project's own, made by `vis_make_skins.py`.

The **meter + spectrum designs** are by **Gelo5**, made for the PeppyMeter screensaver plugin for Volumio (by 2aCD, later foonerd). `vis_install.sh` downloads them from the community template collection that foonerd maintains:

**https://github.com/foonerd/glass_templates**

They are not included in this project and all rights in them remain with their authors. `vis_hybrid_display.py` reads the extra settings those designs carry (where the cover art, text and time go); how the plugin treats those settings was learned from its source, but none of its code is used.

The digital time display on those designs uses the [DSEG](https://github.com/keshikan/DSEG) font by **keshikan**, SIL Open Font License 1.1, also downloaded at install.

## The meter designs (skins)

The skins are by **Gelo5** (the Gelo5-BASIC sets) and **balbuze** (the circular and linear sets), from the PeppyMeterBasic collection that balbuze maintains for Volumio:

**https://github.com/balbuze/Meter-peppymeter**

They are not included in this project. `install.sh` downloads them from that repository, and all rights in them remain with their authors. If you enjoy them, that repository is the place to say thanks, or to contribute designs of your own.

## Roon

- **[pyroon](https://github.com/pavoni/pyroon)** (the `roonapi` Python library) by **Greg Dowling**, Apache License 2.0. `roon_bridge.py` uses it to talk to Roon and to find the Roon Core automatically.
- **Roon Labs** for the Roon extension API.

Roon is a trademark of Roon Labs LLC. This project is not affiliated with or endorsed by Roon Labs.

## Other open-source software

- [pygame](https://www.pygame.org/) and SDL, for drawing.
- [NumPy](https://numpy.org/), for the audio peak and spectrum calculations.
- [Pillow](https://python-pillow.org/), used by PeppySpectrum.
- [pyalsaaudio](https://github.com/larsimmisch/pyalsaaudio), for audio capture.
- [Requests](https://requests.readthedocs.io/), for fetching cover art.
- The [DejaVu fonts](https://dejavu-fonts.github.io/), installed from Raspberry Pi OS.

## How it was made

Andrew Cox (andybob on the Roon Community forum) built this for his own listening room, with a lot of help:

- **Google Gemini** got the project off the ground, with relentless enthusiasm.
- **Claude** (Anthropic) wrote most of the code in this repository with Andrew, and tracked down why the needles wouldn't move.
