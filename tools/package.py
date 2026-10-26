#!/usr/bin/env python3
"""Build the Nexus Mods upload archives from your own game install.

Builds each variant with build.py and zips it as
release/MoreMapMarkers_<limit>-<version>.zip. Inside the zip the files are
laid out from the game root (Stalker2/Content/Paks/~mods/...), so players
can extract the zip straight into the game folder.

Usage:  python tools/package.py --game "<game folder>" [limit ...]   (default: 50 99 999)
"""
import argparse
import os
import sys
import tempfile
import zipfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from build import ROOT, build, find_asset, game_containers  # noqa: E402

DEFAULT_LIMITS = (50, 99, 999)
MODS_DIR = "Stalker2/Content/Paks/~mods"
FIXED_TIME = (2026, 1, 1, 0, 0, 0)  # reproducible archives


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--game", required=True, help="game install folder (contains 'Stalker2')")
    ap.add_argument("limits", type=int, nargs="*", default=DEFAULT_LIMITS)
    args = ap.parse_args()

    with open(os.path.join(ROOT, "VERSION")) as f:
        version = f.read().strip()
    source = find_asset(game_containers(args.game))
    if source is None:
        sys.exit("MapSettingsAsset not found in the game's containers.")
    out = os.path.join(ROOT, "release")
    os.makedirs(out, exist_ok=True)

    for limit in args.limits:
        name = f"MoreMapMarkers_{limit}_P"
        with tempfile.TemporaryDirectory() as tmp:
            build(limit, source, tmp, name)
            path = os.path.join(out, f"MoreMapMarkers_{limit}-{version}.zip")
            with zipfile.ZipFile(path, "w") as zf:
                for ext in ("pak", "utoc", "ucas"):
                    info = zipfile.ZipInfo(f"{MODS_DIR}/{name}.{ext}", FIXED_TIME)
                    info.compress_type = zipfile.ZIP_DEFLATED
                    info.external_attr = 0o644 << 16
                    with open(os.path.join(tmp, f"{name}.{ext}"), "rb") as f:
                        zf.writestr(info, f.read())
        print(f"Wrote {path}")


if __name__ == "__main__":
    main()
