#!/bin/bash
# Roon PeppyMeter Frame - uninstaller
#
# Copyright (C) 2026 Andrew Cox (SoftCox Developments)
# SPDX-License-Identifier: GPL-3.0-or-later
#
# Removes the services, the meter command and the sudoers rule. Leaves this folder
# (settings, skins, PeppyMeter, Roon pairing) and the HDMI setting in cmdline.txt alone,
# so you can delete or keep them as you like.

set -u
echo "Removing Roon PeppyMeter Frame services and the meter command..."
sudo systemctl disable --now rpf-slideshow rpf-display rpf-audio rpf-roon 2>/dev/null
sudo rm -f /etc/systemd/system/rpf-{audio,roon,display,slideshow}.service
sudo rm -f /usr/local/bin/meter /etc/sudoers.d/roon-peppymeter-frame
sudo systemctl daemon-reload
echo "Done. Remember to remove the extension in Roon > Settings > Extensions."
echo "To remove everything else, delete this folder. The HDMI mode setting, if added,"
echo "is in /boot/firmware/cmdline.txt (backup: cmdline.txt.rpf-backup)."
