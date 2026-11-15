#!/bin/bash
# Roon PeppyMeter Frame - VISUALISER EXTENSION - installer
#
# Copyright (C) 2026 Andrew Cox (SoftCox Developments)
# SPDX-License-Identifier: GPL-3.0-or-later
#
# Run from the Roon PeppyMeter Frame install folder, after install.sh:   bash vis_install.sh
# Adds the 'vis' command and a spectrum display. It changes none of the existing files:
# everything it adds is named vis* (plus the PeppySpectrum folder), and vis_uninstall.sh
# removes it again. Safe to run more than once.
set -eu
cd "$(dirname "$(readlink -f "$0")")"
RPF_DIR=$(pwd)
RPF_USER=$(id -un)
PEPPYSPECTRUM_REPO=https://github.com/project-owner/PeppySpectrum

step() { printf '\n== %s\n' "$1"; }
die()  { printf 'ERROR: %s\n' "$1" >&2; exit 1; }

[ "$RPF_USER" != root ] || die "Run as your normal user, not with sudo (it asks for sudo when needed)."
for f in rpf_settings.py frame_display.py settings.conf venv/bin/python; do
    [ -e "$f" ] || die "$f not found here. Run this from the Roon PeppyMeter Frame folder, after install.sh."
done
for f in vis vis_settings.py vis_audio_hub.py vis_spectrum_display.py vis_make_skins.py; do
    [ -f "$f" ] || die "$f is missing - copy all the vis files into $RPF_DIR first."
done
systemctl cat rpf-audio.service >/dev/null 2>&1 || die "rpf-audio.service not found. Run install.sh first."

step "1/5 Fetching PeppySpectrum"
if [ -d PeppySpectrum/.git ]; then
    echo "    PeppySpectrum already present"
else
    git clone --depth 1 "$PEPPYSPECTRUM_REPO" PeppySpectrum
fi
venv/bin/python -c "import PIL" 2>/dev/null || venv/bin/pip install pillow

step "2/5 Making the spectrum skins"
venv/bin/python vis_make_skins.py | grep -v 'pygame\|Hello from'
touch vis_strip.txt

step "3/5 Installing the vis command and the display service"
sed "s|@RPF_DIR@|$RPF_DIR|g" vis | sudo tee /usr/local/bin/vis >/dev/null
sudo chmod 755 /usr/local/bin/vis

sudo tee /etc/systemd/system/rpf-vis.service >/dev/null <<UNITEOF
[Unit]
Description=Roon PeppyMeter Frame - visualiser display (vis)
Wants=rpf-audio.service
After=rpf-audio.service rpf-roon.service rpf-display.service
# Only one program can drive the screen: starting this stops the meters first, and starting
# the meters (any 'meter' switch) stops this.
Conflicts=rpf-display.service

[Service]
Type=simple
User=$RPF_USER
WorkingDirectory=$RPF_DIR
Environment=SDL_VIDEODRIVER=kmsdrm SDL_RENDER_DRIVER=opengles2 PYTHONUNBUFFERED=1
ExecStart=$RPF_DIR/venv/bin/python $RPF_DIR/vis_spectrum_display.py
Restart=always
RestartSec=5
UNITEOF
# No [Install] section on purpose: after a reboot the meters start, as before.

step "4/5 Pointing the audio service at the audio hub"
sudo mkdir -p /etc/systemd/system/rpf-audio.service.d
sudo tee /etc/systemd/system/rpf-audio.service.d/vis.conf >/dev/null <<DROPEOF
# Visualiser extension: run vis_audio_hub.py (peaks for the meters AND spectrum data)
# instead of audio_bridge.py. Delete this file to go back (vis_uninstall.sh does).
[Service]
ExecStart=
ExecStart=$RPF_DIR/venv/bin/python $RPF_DIR/vis_audio_hub.py
DROPEOF

SUDOERS_TMP=$(mktemp)
echo "$RPF_USER ALL=(root) NOPASSWD: /usr/bin/systemctl restart rpf-vis" > "$SUDOERS_TMP"
if sudo visudo -cf "$SUDOERS_TMP" >/dev/null; then
    sudo install -m 440 -o root -g root "$SUDOERS_TMP" /etc/sudoers.d/roon-peppymeter-frame-vis
    echo "    'vis' can switch the display without a password"
else
    echo "    WARNING: sudoers rule failed its check and was not installed; 'vis' will ask for your password"
fi
rm -f "$SUDOERS_TMP"

step "5/5 Restarting the audio service"
sudo systemctl daemon-reload
sudo systemctl restart rpf-audio
sleep 3
printf '    %-12s %s\n' rpf-audio "$(systemctl is-active rpf-audio)"
journalctl -u rpf-audio -n 3 --no-pager 2>/dev/null | sed 's/^/    /' || true

cat <<DONEEOF

Visualiser extension installed. The meters carry on as before.
  vis          lists the visualisers          vis 1     shows the first one
  vis off      back to the meters (so does any 'meter' switch)
  vis --help   everything else
DONEEOF
