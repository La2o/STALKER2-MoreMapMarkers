#!/usr/bin/env python3
"""Build a S.T.A.L.K.E.R. 2 mod that raises the user map marker limit.

The limit is a single int32 property on the cooked asset
/Game/GameLite/FPS_Game/UIRemaster/PDA/WorldMap/MapSettingsAsset
(vanilla value: 10). This script reads that asset straight from your own game
install, patches the value, and writes a new IoStore container (.utoc/.ucas)
plus the empty companion .pak that the game needs to mount it.

Usage:
  python tools/build.py 99 --game "C:/Program Files (x86)/Steam/steamapps/common/S.T.A.L.K.E.R. 2 Heart of Chornobyl"
  python tools/build.py 99 --source path/to/container.utoc
"""
import argparse
import glob
import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from iostore import Container, write_container  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ASSET_SUFFIX = "/GameLite/FPS_Game/UIRemaster/PDA/WorldMap/MapSettingsAsset.uasset"

# The limit's offset from the start of the package's export data. The zen
# package summary stores the header size (= start of export data) at byte 4.
LIMIT_EXPORT_OFFSET = 0x94
VANILLA_LIMIT = 10


def find_asset(utocs):
    for utoc in utocs:
        try:
            c = Container(utoc)
        except ValueError as e:
            print(f"skipping {os.path.basename(utoc)}: {e}", file=sys.stderr)
            continue
        for path, entry in c.files():
            if path.endswith(ASSET_SUFFIX):
                return c, path, entry
    return None


def game_containers(game_dir):
    paks = os.path.join(game_dir, "Stalker2", "Content", "Paks")
    if not os.path.isdir(paks):
        sys.exit(f"Can't find {paks}. Pass the folder that contains 'Stalker2'.")
    # Only the game's own containers, never ~mods.
    return sorted(glob.glob(os.path.join(paks, "*.utoc")))


def patch_limit(package, limit, expect):
    (header_size,) = struct.unpack_from("<I", package, 4)
    offset = header_size + LIMIT_EXPORT_OFFSET
    (current,) = struct.unpack_from("<i", package, offset)
    if current != expect:
        sys.exit(f"Expected the marker limit ({expect}) at {offset:#x}, found {current}. "
                 "The game may have changed this asset; the offset needs updating.")
    package = bytearray(package)
    struct.pack_into("<i", package, offset, limit)
    return bytes(package)


def build(limit, source, out_dir, name, expect=VANILLA_LIMIT):
    container, path, entry = source
    cid = container.chunk_ids[entry]
    package_id = struct.unpack("<Q", cid[:8])[0]
    header = container.container_header()
    if header is None or package_id not in header["entries"]:
        sys.exit(f"{container.path}: no package store entry for {path}")

    package = patch_limit(container.read_chunk(entry), limit, expect)
    mount, fname = path.rsplit("/", 1)
    os.makedirs(out_dir, exist_ok=True)
    write_container(os.path.join(out_dir, name), name, mount + "/", [(fname, cid)],
                    {cid: (package, header["entries"][package_id])})


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("limit", type=int, help="max user markers (vanilla: 10)")
    src = ap.add_mutually_exclusive_group(required=True)
    src.add_argument("--game", help="game install folder (contains 'Stalker2')")
    src.add_argument("--source", help="a specific .utoc that contains the asset")
    ap.add_argument("--out", default=os.path.join(ROOT, "dist"))
    ap.add_argument("--name", help="output base name (default MoreMapMarkers_<limit>_P)")
    ap.add_argument("--expect", type=int, default=VANILLA_LIMIT, help=argparse.SUPPRESS)
    args = ap.parse_args()

    if not 1 <= args.limit <= 0x7FFFFFFF:
        ap.error("limit must be between 1 and 2147483647")
    name = args.name or f"MoreMapMarkers_{args.limit}_P"

    utocs = game_containers(args.game) if args.game else [args.source]
    source = find_asset(utocs)
    if source is None:
        sys.exit("MapSettingsAsset not found in the given containers.")
    print(f"Found {source[1]} in {os.path.basename(source[0].path)}")

    out = os.path.join(args.out, name)
    build(args.limit, source, out, name, args.expect)
    print(f"Built {out} (limit {args.limit})")


if __name__ == "__main__":
    main()
