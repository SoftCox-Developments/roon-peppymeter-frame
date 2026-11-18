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
# Meter + spectrum skin packs (zips from the community template collection), space-separated
HYBRID_PACKS="https://raw.githubusercontent.com/foonerd/glass_templates/main/templates_peppy_spectrum/1920/1080/1920x1080_20g5.zip"
DSEG_ZIP=https://github.com/keshikan/DSEG/releases/download/v0.46/fonts-DSEG_v046.zip

step() { printf '\n== %s\n' "$1"; }
die()  { printf 'ERROR: %s\n' "$1" >&2; exit 1; }

[ "$RPF_USER" != root ] || die "Run as your normal user, not with sudo (it asks for sudo when needed)."
for f in rpf_settings.py frame_display.py settings.conf venv/bin/python; do
    [ -e "$f" ] || die "$f not found here. Run this from the Roon PeppyMeter Frame folder, after install.sh."
done
for f in vis vis_settings.py vis_audio_hub.py vis_spectrum_display.py vis_hybrid_display.py vis_hifi_display.py vis_make_skins.py; do
    [ -f "$f" ] || die "$f is missing - copy all the vis files into $RPF_DIR first."
done
systemctl cat rpf-audio.service >/dev/null 2>&1 || die "rpf-audio.service not found. Run install.sh first."

step "1/6 Fetching PeppySpectrum"
if [ -d PeppySpectrum/.git ]; then
    echo "    PeppySpectrum already present"
else
    git clone --depth 1 "$PEPPYSPECTRUM_REPO" PeppySpectrum
fi
venv/bin/python -c "import PIL" 2>/dev/null || venv/bin/pip install pillow

step "2/6 Making the spectrum skins"
venv/bin/python vis_make_skins.py | grep -v 'pygame\|Hello from'
touch vis_strip.txt

step "3/6 Fetching the meter + spectrum skins"
# Gelo5's combined designs and the digital-clock font they were drawn for. Not part of
# this project: downloaded from their own homes, like the meter skins. If a download
# fails the rest still works; run this installer again later to try again.
venv/bin/python - "$HYBRID_PACKS" "$DSEG_ZIP" <<'PYEOF' || echo "    WARNING: could not fetch everything; the spectrum visualisers still work"
import io, os, sys, urllib.request, zipfile
packs, dseg = sys.argv[1].split(), sys.argv[2]
ok = True
def fetch(url):
    with urllib.request.urlopen(url, timeout=60) as r:
        return r.read()
os.makedirs("vis_hybrid", exist_ok=True)
for url in packs:
    name = os.path.basename(url)[:-4]
    if os.path.isdir(os.path.join("vis_hybrid", name, "templates")):
        print(f"    {name} already present")
        continue
    try:
        print(f"    downloading {name} (about 30 MB) ...", flush=True)
        z = zipfile.ZipFile(io.BytesIO(fetch(url)))
        bad = [n for n in z.namelist() if n.startswith("/") or ".." in n.split("/")]
        if bad:
            raise ValueError("unexpected file names in the zip")
        z.extractall("vis_hybrid")
        print(f"    {name} installed")
    except Exception as e:
        ok = False
        print(f"    {name}: {e}")
font = os.path.join("vis_fonts", "DSEG7Classic-Italic.ttf")
if os.path.isfile(font):
    print("    clock font already present")
else:
    try:
        z = zipfile.ZipFile(io.BytesIO(fetch(dseg)))
        member = [n for n in z.namelist() if n.endswith("/DSEG7Classic-Italic.ttf")][0]
        os.makedirs("vis_fonts", exist_ok=True)
        with open(font, "wb") as f:
            f.write(z.read(member))
        print("    clock font installed")
    except Exception as e:
        ok = False
        print(f"    clock font: {e} (a plain font will be used for the time)")
sys.exit(0 if ok else 1)
PYEOF

step "4/6 Installing the vis command and the display service"
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

step "5/6 Pointing the audio service at the audio hub"
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

step "6/6 Restarting the audio service"
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
