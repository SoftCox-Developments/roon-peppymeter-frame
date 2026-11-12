#!/bin/bash
# Roon PeppyMeter Frame - installer
#
# Copyright (C) 2026 Andrew Cox (SoftCox Developments)
# SPDX-License-Identifier: GPL-3.0-or-later
#
# Run from the project folder as your normal user (not root):   bash install.sh
# Safe to run again after an update: your settings, skins choices and Roon pairing are kept.

set -euo pipefail

RPF_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RPF_USER="$(id -un)"
PIPE=/tmp/rpf_peppy_pipe
PEPPYMETER_REPO=https://github.com/project-owner/PeppyMeter.git
SKINS_REPO=https://github.com/balbuze/Meter-peppymeter.git

step() { echo; echo "==> $*"; }
warn() { echo "    ! $*"; }
die()  { echo; echo "ERROR: $*" >&2; exit 1; }
ask()  { # ask "question" default(Y/N) -> 0 for yes
    local reply def="$2"
    if [ ! -t 0 ]; then [ "$def" = Y ]; return; fi
    read -r -p "    $1 [$( [ "$def" = Y ] && echo Y/n || echo y/N )] " reply
    reply=${reply:-$def}
    [[ "$reply" =~ ^[Yy] ]]
}

[ "$(id -u)" -ne 0 ] || die "Run 'bash install.sh' as your normal user, not with sudo. It asks for sudo when needed."
cd "$RPF_DIR"
echo "Roon PeppyMeter Frame - installing in $RPF_DIR for user $RPF_USER"
sudo -v || die "This installer needs sudo."

step "1/9 Checking for other PeppyMeter services"
if systemctl list-unit-files peppymeter.service 2>/dev/null | grep -q '^peppymeter.service'; then
    warn "A peppymeter.service already exists. Two copies would fight over the screen and audio."
    if ask "Stop and disable peppymeter.service?" Y; then
        sudo systemctl disable --now peppymeter.service || true
    else
        warn "Left running - stop it yourself before using this one."
    fi
else
    echo "    None found."
fi

step "2/9 Installing system packages"
# pygame comes from Debian rather than the Python package site: the Python package site's
# pygame bundles its own SDL without the direct-to-screen (KMS/DRM) support a headless Pi needs.
# The EGL/GLES/Mesa libraries let SDL hand frames to the Pi's GPU.
sudo apt-get update
sudo apt-get install -y git python3-venv python3-dev build-essential libasound2-dev \
    alsa-utils fonts-dejavu-core python3-pygame \
    libegl1 libgles2 libgbm1 libegl-mesa0 libgl1-mesa-dri
for g in audio video render; do
    if getent group "$g" >/dev/null && ! id -nG "$RPF_USER" | grep -qw "$g"; then
        sudo usermod -aG "$g" "$RPF_USER"
        echo "    Added $RPF_USER to group $g"
    fi
done

step "3/9 Fetching PeppyMeter and the skins"
if [ -d PeppyMeter/.git ]; then
    echo "    PeppyMeter already present"
else
    git clone --depth 1 "$PEPPYMETER_REPO" PeppyMeter
fi
if [ -d skins/.git ]; then
    echo "    Skins already present"
else
    git clone --depth 1 "$SKINS_REPO" skins
fi

step "4/9 Python environment (a few minutes the first time)"
echo "    (Orange 'Retrying' warnings mean a download was interrupted and pip is trying again - let it carry on.)"
[ -x venv/bin/python ] || python3 -m venv --system-site-packages venv
# The environment must see Debian's pygame (see step 2), so allow system packages and
# remove any pygame installed into the environment by an earlier version of this installer.
sed -i 's/^include-system-site-packages = false/include-system-site-packages = true/' venv/pyvenv.cfg
if compgen -G "venv/lib/python3*/site-packages/pygame" >/dev/null; then
    venv/bin/pip uninstall -y pygame
fi
venv/bin/pip install --upgrade pip
venv/bin/pip install numpy pyalsaaudio roonapi requests
venv/bin/python -c "import pygame, os; print('    pygame', pygame.version.ver, 'with SDL', '.'.join(map(str, pygame.get_sdl_version())), 'from', os.path.dirname(pygame.__file__))" 2>/dev/null | grep -v 'Hello from' || die "pygame could not be loaded"

step "5/9 Settings"
if [ -f settings.conf ]; then
    echo "    Keeping your settings.conf"
else
    cp settings.conf.example settings.conf
    echo "    Created settings.conf"
fi
if ! grep -q '^device *= *[^ ]' settings.conf; then
    mapfile -t cards < <(arecord -l 2>/dev/null | sed -n 's/^card [0-9]*: \([^ ]*\) \[.*/\1/p' | sort -u)
    if [ ${#cards[@]} -eq 1 ]; then
        sed -i "s|^device *=.*|device = plughw:CARD=${cards[0]},DEV=0|" settings.conf
        echo "    Audio capture device: plughw:CARD=${cards[0]},DEV=0"
    elif [ ${#cards[@]} -eq 0 ]; then
        warn "No audio capture device found. Plug in the USB capture device, then set"
        warn "[audio] device in settings.conf (see 'arecord -l')."
    else
        warn "Several capture devices found (${cards[*]}). Set [audio] device in settings.conf,"
        warn "e.g. device = plughw:CARD=${cards[0]},DEV=0"
    fi
fi
[ -f meter_folders.txt ] || cp default_meter_folders.txt meter_folders.txt
[ -f meter_hidden.txt ] || cp default_meter_hidden.txt meter_hidden.txt
touch meter_strip.txt

step "6/9 Configuring PeppyMeter"
venv/bin/python configure_peppymeter.py

step "7/9 Installing the meter command and services"
sed "s|@RPF_DIR@|$RPF_DIR|g" meter | sudo tee /usr/local/bin/meter >/dev/null
sudo chmod 755 /usr/local/bin/meter

make_fifo="/bin/sh -c '[ -p $PIPE ] || { rm -f $PIPE; mkfifo -m 666 $PIPE; }'"
unit() { sudo tee "/etc/systemd/system/$1.service" >/dev/null; }

unit rpf-audio <<EOF
[Unit]
Description=Roon PeppyMeter Frame - audio capture
After=sound.target

[Service]
Type=simple
User=$RPF_USER
WorkingDirectory=$RPF_DIR
Environment=PYTHONUNBUFFERED=1
ExecStartPre=$make_fifo
ExecStart=$RPF_DIR/venv/bin/python $RPF_DIR/audio_bridge.py
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

unit rpf-roon <<EOF
[Unit]
Description=Roon PeppyMeter Frame - Roon bridge (extension)
Wants=network-online.target
After=network-online.target

[Service]
Type=simple
User=$RPF_USER
WorkingDirectory=$RPF_DIR
Environment=PYTHONUNBUFFERED=1
RuntimeDirectory=roon-peppymeter-frame
RuntimeDirectoryPreserve=yes
ExecStart=$RPF_DIR/venv/bin/python $RPF_DIR/roon_bridge.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF

unit rpf-display <<EOF
[Unit]
Description=Roon PeppyMeter Frame - display
Wants=rpf-audio.service
After=rpf-audio.service rpf-roon.service

[Service]
Type=simple
User=$RPF_USER
WorkingDirectory=$RPF_DIR/PeppyMeter
Environment=SDL_VIDEODRIVER=kmsdrm SDL_RENDER_DRIVER=opengles2 PYTHONUNBUFFERED=1
ExecStartPre=$make_fifo
ExecStart=$RPF_DIR/venv/bin/python $RPF_DIR/frame_display.py
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

unit rpf-slideshow <<EOF
[Unit]
Description=Roon PeppyMeter Frame - skin slideshow (meter slideshow)
After=rpf-display.service

[Service]
Type=simple
User=$RPF_USER
ExecStart=/usr/local/bin/meter _loop
Restart=on-failure

[Install]
WantedBy=multi-user.target
EOF

SUDOERS_TMP=$(mktemp)
echo "$RPF_USER ALL=(root) NOPASSWD: /usr/bin/systemctl restart rpf-display, /usr/bin/systemctl enable --now rpf-slideshow, /usr/bin/systemctl disable --now rpf-slideshow, /usr/bin/systemctl restart rpf-slideshow" > "$SUDOERS_TMP"
if sudo visudo -cf "$SUDOERS_TMP" >/dev/null; then
    sudo install -m 440 -o root -g root "$SUDOERS_TMP" /etc/sudoers.d/roon-peppymeter-frame
    echo "    'meter' can restart the display without a password"
else
    warn "sudoers rule failed its check and was not installed; 'meter' will ask for your password"
fi
rm -f "$SUDOERS_TMP"
sudo systemctl daemon-reload
sudo systemctl enable rpf-audio rpf-roon rpf-display >/dev/null

step "8/9 HDMI output mode"
CMDLINE=/boot/firmware/cmdline.txt
W=$(sed -n 's/^width *= *//p' settings.conf | tr -d ' '); W=${W:-1920}
H=$(sed -n 's/^height *= *//p' settings.conf | tr -d ' '); H=${H:-1080}
if [ ! -f "$CMDLINE" ]; then
    warn "$CMDLINE not found - skipping. Set your screen to ${W}x${H} yourself."
elif grep -q 'video=HDMI' "$CMDLINE"; then
    echo "    Already set: $(grep -o 'video=HDMI[^ ]*' "$CMDLINE")"
else
    echo "    Without this, the Pi may run the screen at the TV's own preferred mode (often 4K at 30 Hz)."
    if ask "Set HDMI-A-1 to ${W}x${H} at 60 Hz? (takes effect after a reboot)" Y; then
        sudo cp "$CMDLINE" "$CMDLINE.rpf-backup"
        sudo sed -i "1 s/\$/ video=HDMI-A-1:${W}x${H}@60/" "$CMDLINE"
        echo "    Done (backup: $CMDLINE.rpf-backup)"
        REBOOT_NEEDED=1
    fi
fi

step "9/9 Starting"
sudo systemctl restart rpf-roon rpf-audio
sleep 3
sudo systemctl restart rpf-display
sleep 5
for s in rpf-audio rpf-roon rpf-display; do
    printf '    %-12s %s\n' "$s" "$(systemctl is-active $s)"
done

ZONE=$(sed -n 's/^zone *= *//p' settings.conf | tr -d '\r')
cat <<EOF

Installed. Next:
  1. In Roon: Settings > Extensions > enable "$(sed -n 's/^extension_name *= *//p' settings.conf)".
EOF
if [ -z "$ZONE" ]; then
cat <<EOF
  2. Choose the zone to follow. The zones Roon can see are listed by:
        journalctl -u rpf-roon -n 20 --no-pager
     Put one in settings.conf under [roon] (zone = ...), then:
        sudo systemctl restart rpf-roon
EOF
fi
cat <<EOF
  3. Play some music. 'meter' lists the skins; 'meter --help' shows what it can do.
EOF
[ "${REBOOT_NEEDED:-0}" = 1 ] && echo "  4. Reboot when convenient (sudo reboot) to apply the HDMI mode."
echo
