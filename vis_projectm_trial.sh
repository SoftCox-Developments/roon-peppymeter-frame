#!/bin/bash
# Roon PeppyMeter Frame - VISUALISER EXTENSION - projectM TRIAL: run
#
# Copyright (C) 2026 Andrew Cox (SoftCox Developments)
# SPDX-License-Identifier: GPL-3.0-or-later
#
# Takes the screen from the meters / visualiser, runs vis_projectm_trial.py, and puts the
# previous display back afterwards (also after Ctrl-C). Options are passed on, e.g.
#   bash vis_projectm_trial.sh --size 960x360
#   bash vis_projectm_trial.sh --full --count 20
#   bash vis_projectm_trial.sh --help
cd "$(dirname "$(readlink -f "$0")")"
case " $* " in *" -h "*|*" --help "*) venv/bin/python vis_projectm_trial.py --help; exit 0 ;; esac
WAS=rpf-display
systemctl is-active --quiet rpf-vis && WAS=rpf-vis
sudo systemctl stop rpf-vis rpf-display
trap 'echo; echo "Putting the display back ($WAS)..."; sudo systemctl restart $WAS' EXIT
SDL_VIDEODRIVER=kmsdrm venv/bin/python vis_projectm_trial.py "$@"
