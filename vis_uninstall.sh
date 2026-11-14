#!/bin/bash
# Roon PeppyMeter Frame - VISUALISER EXTENSION - uninstaller
#
# Copyright (C) 2026 Andrew Cox (SoftCox Developments)
# SPDX-License-Identifier: GPL-3.0-or-later
#
# Puts the system back to plain Roon PeppyMeter Frame: the audio service runs
# audio_bridge.py again and the meters return. Leaves the vis files, vis_skins and
# PeppySpectrum in this folder (delete them yourself if you like).
set -u
echo "Removing the visualiser extension's service, command and audio drop-in..."
sudo systemctl stop rpf-vis 2>/dev/null
sudo rm -f /etc/systemd/system/rpf-vis.service /etc/systemd/system/rpf-audio.service.d/vis.conf
sudo rmdir /etc/systemd/system/rpf-audio.service.d 2>/dev/null
sudo rm -f /usr/local/bin/vis /etc/sudoers.d/roon-peppymeter-frame-vis
sudo systemctl daemon-reload
sudo systemctl restart rpf-audio
sleep 3
sudo systemctl restart rpf-display
echo "Done. rpf-audio: $(systemctl is-active rpf-audio), rpf-display: $(systemctl is-active rpf-display)"
