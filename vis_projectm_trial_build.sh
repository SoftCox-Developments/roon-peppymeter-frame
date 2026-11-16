#!/bin/bash
# Roon PeppyMeter Frame - VISUALISER EXTENSION - projectM TRIAL: build and download
#
# Copyright (C) 2026 Andrew Cox (SoftCox Developments)
# SPDX-License-Identifier: GPL-3.0-or-later
#
# A trial to find out how well projectM (the MilkDrop visualiser) runs on this computer.
# Builds the projectM library from source and downloads a preset pack, all inside the
# folder vis_projectm/. Nothing already installed is changed; delete vis_projectm/ to undo.
# Run from the install folder:   bash vis_projectm_trial_build.sh
set -eu
cd "$(dirname "$(readlink -f "$0")")"
[ "$(id -un)" != root ] || { echo "Run as your normal user, not with sudo."; exit 1; }
[ -f rpf_settings.py ] || { echo "Run this from the Roon PeppyMeter Frame folder."; exit 1; }

# Pinned versions: projectM development (4.2.0) - the released 4.1.8 cannot draw into part of the screen
PROJECTM_REPO=https://github.com/projectM-visualizer/projectm
PROJECTM_COMMIT=eae22de40144ee8ded92f3c04b93a4c2f82adcc0
PRESETS_REPO=https://github.com/projectM-visualizer/presets-cream-of-the-crop
TEXTURES_REPO=https://github.com/projectM-visualizer/presets-milkdrop-texture-pack

step() { printf '\n== %s\n' "$1"; }
D=vis_projectm
mkdir -p "$D"

step "1/4 Installing build tools (asks for your password)"
sudo apt-get install -y git cmake g++ ninja-build libgles-dev libegl-dev

step "2/4 Fetching projectM source"
if [ -f "$D/src/CMakeLists.txt" ]; then
    echo "    already present"
else
    git init -q "$D/src"
    git -C "$D/src" remote add origin "$PROJECTM_REPO"
    git -C "$D/src" fetch -q --depth 1 origin "$PROJECTM_COMMIT"
    git -C "$D/src" checkout -q FETCH_HEAD
    git -C "$D/src" submodule update --init --depth 1
fi

step "3/4 Building the library (several minutes; two jobs at a time to suit 1 GB of memory)"
if [ -f "$D/inst/lib/libprojectM-4.so.4" ]; then
    echo "    already built"
else
    START=$(date +%s)
    cmake -S "$D/src" -B "$D/build" -G Ninja -DCMAKE_BUILD_TYPE=Release -DENABLE_GLES=ON \
          -DBUILD_TESTING=OFF -DCMAKE_INSTALL_PREFIX="$PWD/$D/inst" | grep -E 'OpenGL ES|Configuring done|rror' || true
    ninja -C "$D/build" -j2 install | tail -n 1
    echo "    built in $(( $(date +%s) - START )) seconds"
fi
ls -l "$D/inst/lib/libprojectM-4.so.4"

step "4/4 Downloading presets (about 130 MB) and textures"
[ -d "$D/presets/.git" ]  && echo "    presets already present"  || git clone -q --depth 1 "$PRESETS_REPO" "$D/presets"
[ -d "$D/textures/.git" ] && echo "    textures already present" || git clone -q --depth 1 "$TEXTURES_REPO" "$D/textures"
echo "    $(find "$D/presets" -name '*.milk' | wc -l) presets"

cat <<DONEEOF

Ready. Next (with music playing):
  sudo systemctl restart rpf-audio          the audio hub with the new audio feed
  bash vis_projectm_trial.sh                the trial itself: about 10 minutes, Ctrl-C to stop early
DONEEOF
