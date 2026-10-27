#!/usr/bin/env python3
"""Build a S.T.A.L.K.E.R. 2 mod that raises the user map marker limit.

The limit is the int32 property PlayerLandmarksLimitTotal on the cooked asset
/Game/GameLite/FPS_Game/UIRemaster/PDA/WorldMap/MapSettingsAsset
(vanilla value: 10). This script reads that asset straight from your own game
install, sets the value, and writes a new IoStore container (.utoc/.ucas)
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

# The asset's single export uses unversioned property serialization: a header
# of fragments listing which properties are present, an optional zero mask,
# then the values of the present properties in order. Properties that equal
# the class default are left out, and since the game's 1.x updates that
# includes the limit, so it may have to be inserted rather than overwritten.
LIMIT_PROPERTY = 17          # PlayerLandmarksLimitTotal
PROPERTIES_BEFORE_LIMIT = (1, 3, 5, 6, 8, 9, 10, 11, 12, 13, 16)
VALUES_BEFORE_LIMIT = 0x89   # serialized size of the properties above
ARRAY_COUNT_OFFSET = 0x21    # property 16 is an array of 5 structs
ARRAY_COUNT = 5
VANILLA_LIMIT = 10

# Zen package summary fields.
SUMMARY_HEADER_SIZE = 4      # header size = start of export data
SUMMARY_EXPORT_MAP = 0x20
SUMMARY_EXPORT_BUNDLES = 0x24
EXPORT_ENTRY_SIZE = 72       # FExportMapEntry; CookedSerialSize is at +8


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


def read_properties(package):
    """Parse the export's unversioned property header.

    Returns (present, zeroed, frags_end, values_start): the present property
    indices in order, the subset that sits in fragments with a zero mask, the
    end of the fragments (where the zero mask starts) and the offset of the
    first value.
    """
    pos = struct.unpack_from("<I", package, SUMMARY_HEADER_SIZE)[0]
    present, zeroed, n_zero = [], set(), 0
    index = 0
    while True:
        (frag,) = struct.unpack_from("<H", package, pos)
        pos += 2
        index += frag & 0x7F
        count = frag >> 9
        for i in range(index, index + count):
            present.append(i)
            if frag & 0x80:
                zeroed.add(i)
        if frag & 0x80:
            n_zero += count
        index += count
        if frag & 0x100:
            break
    frags_end = pos
    if n_zero:
        pos += 1 if n_zero <= 8 else 2 if n_zero <= 16 else 4 * ((n_zero + 31) // 32)
    return present, zeroed, frags_end, pos


def write_fragments(present, zeroed):
    out = bytearray()
    prev = 0
    runs = []
    for i in present:
        z = i in zeroed
        if runs and runs[-1][0] + runs[-1][1] == i and runs[-1][2] == z and runs[-1][1] < 127:
            runs[-1][1] += 1
        else:
            runs.append([i, 1, z])
    for n, (start, count, z) in enumerate(runs):
        skip = start - prev
        if skip > 127:
            raise ValueError("property gap too large for one fragment")
        out += struct.pack("<H", skip | (0x80 if z else 0) | (0x100 if n == len(runs) - 1 else 0) | count << 9)
        prev = start + count
    return bytes(out)


def check_layout(package, present, values_start):
    if tuple(i for i in present if i < LIMIT_PROPERTY) != PROPERTIES_BEFORE_LIMIT or \
            struct.unpack_from("<i", package, values_start + ARRAY_COUNT_OFFSET)[0] != ARRAY_COUNT:
        sys.exit("MapSettingsAsset doesn't have the expected layout. "
                 "The game may have changed this asset; the build needs updating.")


def read_limit(package):
    """The serialized limit, or None when the asset leaves it at the class default."""
    present, _, _, values_start = read_properties(package)
    check_layout(package, present, values_start)
    if LIMIT_PROPERTY not in present:
        return None
    return struct.unpack_from("<i", package, values_start + VALUES_BEFORE_LIMIT)[0]


def patch_limit(package, limit, expect):
    present, zeroed, frags_end, values_start = read_properties(package)
    check_layout(package, present, values_start)
    export_start = struct.unpack_from("<I", package, SUMMARY_HEADER_SIZE)[0]
    offset = values_start + VALUES_BEFORE_LIMIT
    package = bytearray(package)

    if LIMIT_PROPERTY in present:
        (current,) = struct.unpack_from("<i", package, offset)
        if current != expect:
            sys.exit(f"Expected the marker limit ({expect}), found {current}. "
                     "The game may have changed this asset; the build needs updating.")
        struct.pack_into("<i", package, offset, limit)
        return bytes(package)

    # The limit is at its default (assumed to be the vanilla value): add it to
    # the property header and insert its value after property 16. Property 17
    # has no zero mask bit, so the mask stays as it is.
    export_map, bundles = struct.unpack_from("<ii", package, SUMMARY_EXPORT_MAP)
    if bundles - export_map != EXPORT_ENTRY_SIZE:
        sys.exit("MapSettingsAsset has more than one export; the build needs updating.")
    frags = write_fragments(sorted(present + [LIMIT_PROPERTY]), zeroed)
    package[offset:offset] = struct.pack("<i", limit)
    package[export_start:frags_end] = frags

    # The export map stores the export's serialized size.
    delta = len(frags) - (frags_end - export_start) + 4
    (size,) = struct.unpack_from("<Q", package, export_map + 8)
    struct.pack_into("<Q", package, export_map + 8, size + delta)
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
