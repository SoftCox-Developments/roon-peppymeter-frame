#!/usr/bin/env python3
# Roon PeppyMeter Frame - Roon bridge (a Roon extension)
#
# Copyright (C) 2026 Andrew Cox (SoftCox Developments)
# SPDX-License-Identifier: GPL-3.0-or-later
#
# This program is free software: you can redistribute it and/or modify it under the terms of
# the GNU General Public License as published by the Free Software Foundation, either
# version 3 of the License, or (at your option) any later version. See LICENSE.
#
# Uses pyroon (roonapi) by Greg Dowling, Apache License 2.0: https://github.com/pavoni/pyroon
"""Roon extension that follows one zone and writes now-playing info for the display.

Writes to a RAM folder (see rpf_settings.META_DIR):
  now_playing.json  state, title, artist, album, position, length, image_key, art_key
  current_art.jpg   album art, up to 1080 px
art_key names the artwork actually in current_art.jpg, so the display never
shows the previous track's art while a new one downloads.

The Roon Core is found automatically unless [roon] core_ip is set in settings.conf.
"""
import json
import os
import queue
import sys
import threading
import time

import requests
from roonapi import RoonApi, RoonDiscovery

import rpf_settings

S = rpf_settings.load()
ZONE = S.get("roon", "zone")
CORE_IP = S.get("roon", "core_ip")
CORE_PORT = S.getint("roon", "core_port")
JSON_FILE = rpf_settings.JSON_FILE
ART_FILE = rpf_settings.ART_FILE
TOKEN_FILE = rpf_settings.TOKEN_FILE
ART_SIZE = 1080
STARTUP_TIMEOUT = 30

APPINFO = {
    "extension_id": "com.softcox.roonpeppymeterframe",
    "display_name": S.get("roon", "extension_name") or "Frame Display Bridge",
    "display_version": "2.0.0",
    "publisher": "SoftCox Developments",
    "email": "",
    "website": "https://github.com/SoftCox-Developments/roon-peppymeter-frame",
}

HOW_TO_SET_ZONE = (f"To choose a zone from a list, run 'bash install.sh' again in {rpf_settings.BASE_DIR} "
                   f"(safe to repeat). Or set 'zone = ...' under [roon] in {rpf_settings.SETTINGS_FILE}, "
                   "then: sudo systemctl restart rpf-roon")

lock = threading.Lock()
info = {"state": "stopped", "title": None, "artist": None, "album": None,
        "position": None, "length": None, "image_key": None, "art_key": None,
        "updated": 0}
art_queue = queue.Queue()
roon = None
core = (None, None)          # (host, port) of the connected Core
zone_id = None
zone_warned = False


def log(msg):
    print(msg, flush=True)


def write_json():
    os.makedirs(rpf_settings.META_DIR, exist_ok=True)
    with lock:
        info["updated"] = time.time()
        tmp = JSON_FILE + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(info, f, ensure_ascii=False)
        os.replace(tmp, JSON_FILE)


def write_zones(zones):
    """List the zone names Roon can see, one per line, for install.sh to offer."""
    os.makedirs(rpf_settings.META_DIR, exist_ok=True)
    names = sorted(z.get("display_name", "?") for z in zones.values())
    tmp = rpf_settings.ZONES_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write("\n".join(names) + "\n")
    os.replace(tmp, rpf_settings.ZONES_FILE)


def art_worker():
    while True:
        key = art_queue.get()
        try:
            url = (f"http://{core[0]}:{core[1]}/api/image/{key}"
                   f"?scale=fit&width={ART_SIZE}&height={ART_SIZE}")
            r = requests.get(url, timeout=10)
            r.raise_for_status()
            os.makedirs(rpf_settings.META_DIR, exist_ok=True)
            tmp = ART_FILE + ".tmp"
            with open(tmp, "wb") as f:
                f.write(r.content)
            os.replace(tmp, ART_FILE)
            with lock:
                current = info["image_key"] == key
                if current:
                    info["art_key"] = key
            if current:
                write_json()
        except Exception as e:
            log(f"Artwork download failed: {e}")


def find_zone(zones):
    global zone_warned
    names = sorted(z.get("display_name", "?") for z in zones.values())
    if not ZONE:
        if not zone_warned:
            log("No zone set. Zones Roon can see: " + ", ".join(names))
            log(HOW_TO_SET_ZONE)
            zone_warned = True
        return None
    zid = next((k for k, z in zones.items() if z.get("display_name") == ZONE), None)
    if zid is None and not zone_warned:
        log(f"Zone '{ZONE}' not found (yet). Zones Roon can see: " + ", ".join(names))
        log(HOW_TO_SET_ZONE)
        zone_warned = True
    return zid


def on_change(event, changed_ids):
    global zone_id
    zones = roon.zones
    if zone_id not in zones:
        zone_id = find_zone(zones)
        if zone_id is None:
            return
        log(f"Following zone '{ZONE}' ({zone_id})")
    if event != "toplevel" and zone_id not in (changed_ids or []):
        return

    zone = zones.get(zone_id) or {}
    np = zone.get("now_playing") or {}
    roon_state = zone.get("state", "stopped")
    if not np or roon_state == "stopped":
        state = "stopped"
    elif roon_state == "paused":
        state = "paused"
    else:
        state = "playing"   # playing or loading

    lines = np.get("three_line") or {}
    pos = zone.get("seek_position")
    if pos is None:
        pos = np.get("seek_position")
    key = np.get("image_key")

    with lock:
        title_changed = lines.get("line1") != info["title"]
        art_changed = key != info["image_key"]
        info.update(state=state, title=lines.get("line1"), artist=lines.get("line2"),
                    album=lines.get("line3"), position=pos, length=np.get("length"),
                    image_key=key)
        if art_changed:
            info["art_key"] = None
    if title_changed and info["title"]:
        log(f"Now playing: {info['title']} - {info['artist']}")
    if art_changed and key:
        art_queue.put(key)
    write_json()


def load_saved():
    try:
        with open(TOKEN_FILE) as f:
            return json.load(f)
    except Exception:
        return {}


def connect():
    global core
    saved = load_saved()
    token = saved.get("token")

    if CORE_IP:
        core = (CORE_IP, CORE_PORT)
        log(f"Using Roon Core at {CORE_IP}:{CORE_PORT} (from settings.conf)")
    else:
        log("Looking for the Roon Core on the network...")
        discover = RoonDiscovery(saved.get("core_id"))
        core = discover.first()
        discover.stop()
        if not core[0]:
            log(f"No Roon Core found. Check the network, or set [roon] core_ip in {rpf_settings.SETTINGS_FILE}")
            sys.exit(1)
        log(f"Found Roon Core at {core[0]}:{core[1]}")

    if not token:
        log(f"Not paired yet: enable '{APPINFO['display_name']}' in Roon > Settings > Extensions")
    api = RoonApi(APPINFO, token, core[0], core[1])
    if api.token and (api.token != token or api.core_id != saved.get("core_id")):
        with open(TOKEN_FILE, "w") as f:
            json.dump({"token": api.token, "core_id": api.core_id}, f)
        os.chmod(TOKEN_FILE, 0o600)
        log("Saved Roon pairing")
    return api


def main():
    global roon
    os.makedirs(rpf_settings.META_DIR, exist_ok=True)
    write_json()
    threading.Thread(target=art_worker, daemon=True).start()

    roon = connect()
    deadline = time.monotonic() + STARTUP_TIMEOUT
    while not roon.zones and time.monotonic() < deadline:
        time.sleep(1)
    if not roon.zones:
        log(f"No zones from Roon after {STARTUP_TIMEOUT} s; exiting so systemd retries")
        sys.exit(1)

    log(f"Connected; {len(roon.zones)} zones visible")
    write_zones(roon.zones)
    roon.register_state_callback(on_change)
    on_change("toplevel", [])
    while True:
        time.sleep(10)


if __name__ == "__main__":
    main()
