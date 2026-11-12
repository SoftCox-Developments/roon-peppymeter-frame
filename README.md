# Roon PeppyMeter Frame

Classic VU meters on a TV or monitor, driven by whatever Roon is playing, with the track, artist, album, progress and cover art shown alongside, and the album art filling the screen when you pause.

It runs on a Raspberry Pi 4 behind the screen. The needles move with the **actual analogue output of your DAC**, so they show exactly what you hear, whatever the source and whatever DSP, upsampling or HQPlayer processing sits in between. The track details come from Roon through a small Roon extension.

<img width="640" height="480" alt="Meters 1" src="https://github.com/user-attachments/assets/f2b0061e-d538-475c-b4a2-32cbe2d5072e" />

<img width="640" height="480" alt="Meters 2" src="https://github.com/user-attachments/assets/25af04cd-4a64-4e90-b494-9a06ee6d9c4a" />

<img width="640" height="480" alt="Meters 3" src="https://github.com/user-attachments/assets/283545ce-5221-4adc-9616-0e90368c06b2" />

<img width="640" height="480" alt="Meters 4" src="https://github.com/user-attachments/assets/7ef0a456-ee75-4b1b-978c-a90a20b9a35b" />

## Features

- **Live VU meters** from [PeppyMeter](https://github.com/project-owner/PeppyMeter), redrawn 60 times a second.
- **Now playing** strip: title, artist, album, a progress bar with elapsed/total time (hidden for internet radio and other streams without a length), and cover art.
- **Paused**: the meters give way to large cover art. **Stopped**: the meters stay, and the strip clears.
- **Dozens of meter designs** from the PeppyMeter skin collection by Gelo5 and balbuze, at 1920x1080, 1920x720, 1920x515 and 1920x480. The strip fits itself to each one: under the shorter designs it uses the free space and grows to suit.
- **The `meter` command** to choose a design by number, step through them, pick at random, run a slideshow, hide the ones you don't like, nudge a design up or down, and darken the strip behind the text.
- **Starts by itself** at power-on and finds your Roon Core automatically.
- Everything that changes all the time lives in memory, not on the SD card.

## What you need

| | Tested with | Notes |
|---|---|---|
| Raspberry Pi | Pi 4 Model B, 1 GB | Uses about a third of one core at 60 fps. |
| Operating system | Raspberry Pi OS Lite 64-bit (Debian 13 "trixie") | No desktop needed. |
| USB audio capture | Behringer UCA222 | Any USB line-in that Linux recognises should work. |
| A second analogue output | DAC with both XLR and RCA outputs | The meters need their own line-level feed: a spare DAC output, a preamp's tape/record out, or a splitter. |
| Screen | Samsung Frame TV, 1920x1080 | Any HDMI screen. |
| Roon | Roon 2.x | The extension follows one zone. |

## How it works

```
 DAC analogue out ──> USB capture ──> audio_bridge ──(peak levels via a pipe)──> PeppyMeter ─┐
                                                                                             ├─> HDMI
 Roon Core ──> roon_bridge (Roon extension) ──> now-playing info + art (in RAM) ──> overlay ──┘
```

Three small services run on the Pi:

| Service | Program | Job |
|---|---|---|
| `rpf-audio` | `audio_bridge.py` | Reads the capture device and sends left/right peak levels to PeppyMeter, 120 times a second |
| `rpf-roon` | `roon_bridge.py` | The Roon extension: follows your zone, saves title, artist, album, position and art |
| `rpf-display` | `frame_display.py` | Runs PeppyMeter (unmodified) with the now-playing overlay drawn on top |

A fourth, `rpf-slideshow`, runs only while `meter slideshow` is switched on.

## Installing

### 1. Prepare the Pi

1. Use [Raspberry Pi Imager](https://www.raspberrypi.com/software/) to put **Raspberry Pi OS Lite (64-bit)** on a microSD card. In its settings, choose a username and password, turn on **SSH**, and set up Wi-Fi if you're not using Ethernet (Ethernet is recommended).
2. Connect the Pi's HDMI port nearest the power socket (HDMI 0) to the screen, plug in the USB capture device, and run a cable from your DAC's spare analogue output to the capture device's input.
3. Start the Pi and log in over SSH.

### 2. Download and install

```
sudo apt update && sudo apt install -y git
git clone https://github.com/SoftCox-Developments/roon-peppymeter-frame.git
cd roon-peppymeter-frame
bash install.sh
```

The installer takes a few minutes the first time. It:

1. Offers to stop any existing `peppymeter` service, so two copies don't fight over the screen.
2. Installs the system packages it needs (Python tools, ALSA, the DejaVu font).
3. Downloads [PeppyMeter](https://github.com/project-owner/PeppyMeter) and the [skin collection](https://github.com/balbuze/Meter-peppymeter) from their own GitHub pages. Neither is included in this project.
4. Sets up a private Python environment in `venv/`.
5. Creates `settings.conf`, and fills in your capture device if it finds exactly one.
6. Points PeppyMeter at the skins, the screen size and the audio pipe (keeping a copy of its original `config.txt`).
7. Installs the `meter` command and the services, and a sudoers rule that lets `meter` restart the display without a password.
8. Offers to fix the HDMI output at 1920x1080, 60 Hz. Without this, many TVs end up at 4K/30 Hz.
9. Starts everything.

### 3. Connect to Roon

1. In Roon, go to **Settings > Extensions** and enable **Frame Display Bridge**.
2. Choose the zone the meters should follow. The extension lists the zones it can see:
   ```
   journalctl -u rpf-roon -n 20 --no-pager
   ```
   Put the name, exactly as Roon shows it, in `settings.conf`:
   ```
   nano settings.conf
   ```
   ```
   [roon]
   zone = Living Room
   ```
   Save (Ctrl+O, Enter, Ctrl+X), then:
   ```
   sudo systemctl restart rpf-roon
   ```
3. If you let the installer set the HDMI mode, reboot once: `sudo reboot`.

Play something, and the meters and track details should appear.

## Settings

Everything you might need to change is in `settings.conf`, with comments explaining each line. The main ones:

| Setting | Default | |
|---|---|---|
| `[roon] zone` | (empty) | The Roon zone to follow |
| `[roon] core_ip` | (empty) | Leave empty to find the Core automatically; set it if discovery doesn't work on your network |
| `[roon] extension_name` | Frame Display Bridge | The name shown in Roon |
| `[audio] device` | (set by installer) | e.g. `plughw:CARD=CODEC,DEV=0`; list devices with `arecord -l` |
| `[display] width`, `height` | 1920, 1080 | Screen size |
| `[display] dim_level` | 150 | How dark `meter strip dim` is (0-255, higher is darker) |

After a change, restart the part concerned: `sudo systemctl restart rpf-roon`, `rpf-audio` or `rpf-display`.

## Choosing meters: the `meter` command

```
meter                 list the meters, numbered; * marks the one on screen
meter 12              switch to number 12
meter next / prev     step through the list
meter random          pick one at random
meter slideshow 15    a random meter every 15 minutes while music plays (meter slideshow off to stop)
meter hide            hide the meter on screen from the list (meter unhide to bring meters back)
meter shift -250      move the meter on screen up 250 pixels (meter shift 0 puts it back)
meter strip dim       darken the background behind the track details (clear, dim or black)
meter --help          everything else
```

A few tips:

- **Full-screen designs** (the 1920x1080 Gelo5 set) fill the whole screen, so the track details sit over the lower part of the picture. Try `meter shift -250` to lift the design and free a clean strip at the bottom. Values like `-300` or more give a taller strip with bigger text. For designs too pretty to move, `meter strip dim` or `meter strip black` keeps the text readable instead.
- **Shorter designs** (1920x720, 515 and 480) sit at the top of the screen with the track details below them.
- `shift` and `strip` are remembered for each design, so they're there again after a switch, a slideshow change or a restart.
- Some lower-resolution duplicates and the linear "fluo" designs are hidden by default. `meter unhide` lists them.
- The list of design folders is in `meter_folders.txt`. Other 1920-wide folders from the skin collection can be added there.

## Troubleshooting

Each service writes a log. These show the latest lines:

```
journalctl -u rpf-audio -n 20 --no-pager
journalctl -u rpf-roon -n 20 --no-pager
journalctl -u rpf-display -n 20 --no-pager
```

**The needles don't move.** Check the audio is reaching the Pi. Stop the meters, run a 10-second level test with music playing, then start them again:
```
sudo systemctl stop rpf-display rpf-audio
arecord -D plughw:CARD=CODEC,DEV=0 -f S16_LE -r 44100 -c 2 -d 10 -V stereo /dev/null
sudo systemctl start rpf-audio rpf-display
```
(Use your own device name from `settings.conf`.) The text meter should swing with the music. If it doesn't, check the cable and that the DAC output is live. If the level is very low, check whether volume is being reduced digitally before the DAC.

**No track details.** Check the extension is enabled in Roon and the zone name in `settings.conf` matches exactly. The `rpf-roon` log lists the zones it can see.

**The extension doesn't appear in Roon.** Automatic discovery may be blocked on your network. Set `core_ip` in `settings.conf` to your Roon Core's address and restart `rpf-roon`.

**The picture is the wrong size or blurry.** Check the HDMI mode: `cat /sys/class/graphics/fb0/virtual_size` should say `1920,1080`. Your TV's info screen should report 1080p at 60 Hz.

**Checking the Pi is comfortable:**
```
ps -o pid,pcpu,rss,etime,cmd -C python
vcgencmd measure_temp; vcgencmd get_throttled
```
`throttled=0x0` means the Pi has never slowed down for heat or power.

## Notes from the field

A few things worth knowing if you build on this:

- **PeppyMeter's pipe reader has a speed limit.** It reads one record, pauses for a tenth of its polling interval, and repeats until the pipe is empty. Feed it much faster than it can drain (a few hundred records a second at 60 fps) and it never gets to the end, so the needles freeze. Feed it slower than it polls and it reads an empty pipe as silence, so the needles dip. `audio_bridge.py` sends 120 peak readings a second for PeppyMeter's 60 polls.
- **PeppyMeter takes the screen size from the skin folder's name**, so a `1920x720-...` folder would otherwise open a 1920x720 screen. This project sets the size from `settings.conf` instead.
- **Pasting multi-line commands into an SSH window** can go wrong when `sudo` stops to ask for a password: the next pasted lines get swallowed. Run `sudo -v` on its own first, or wrap blocks in `{ ... }`.
- **Roon's extension API doesn't share the waveform** shown in Roon's seek bar, so the progress bar is a plain line.

## Uninstalling

```
bash uninstall.sh
```
This removes the services, the `meter` command and the sudoers rule. It leaves this folder and the HDMI setting alone (see the script's message for where those are), and you can remove the extension in Roon's settings.

## Credits and licence

This project stands on the work of others. See [CREDITS.md](CREDITS.md).

Copyright (C) 2026 Andrew Cox (SoftCox Developments).

This program is free software: you can redistribute it and/or modify it under the terms of the GNU General Public License as published by the Free Software Foundation, either version 3 of the License, or (at your option) any later version. It is distributed in the hope that it will be useful, but WITHOUT ANY WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See [LICENSE](LICENSE).

Roon is a trademark of Roon Labs LLC. This project is not affiliated with or endorsed by Roon Labs.
