#!/usr/bin/env python3
"""Read back a built container the way the IoStore reader does and check it.

Checks the perfect-hash lookup of every chunk, the chunk hashes, the
directory index and the container header, then prints the marker limit.

Usage:  python tools/verify.py dist/MoreMapMarkers_99_P/MoreMapMarkers_99_P.utoc
"""
import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from build import LIMIT_EXPORT_OFFSET  # noqa: E402
from iostore import CHUNK_EXPORT_BUNDLE_DATA, Container, Reader, hash_chunk_id  # noqa: E402


def seeds(c):
    toc = open(c.path, "rb").read()
    n = struct.unpack_from("<I", toc, 0x54)[0]
    start = 0x90 + 22 * len(c.chunk_ids)
    return [struct.unpack_from("<i", toc, start + 4 * i)[0] for i in range(n)]


def lookup(c, s, cid):
    seed = s[hash_chunk_id(0, cid) % len(s)]
    if seed == 0:
        return None
    slot = -seed - 1 if seed < 0 else hash_chunk_id(seed, cid) % len(c.chunk_ids)
    return slot if c.chunk_ids[slot] == cid else None


def main(utoc):
    c = Container(utoc)
    s = seeds(c)
    for i, cid in enumerate(c.chunk_ids):
        assert lookup(c, s, cid) == i, f"chunk {i} not reachable via perfect hash"
        c.read_chunk(i)  # raises on hash mismatch
    print(f"{len(c.chunk_ids)} chunks: lookup and hashes OK")

    header = c.container_header()
    files = list(c.files())
    assert files, "empty directory index"
    for path, entry in files:
        cid = c.chunk_ids[entry]
        assert cid[11] == CHUNK_EXPORT_BUNDLE_DATA
        pid = struct.unpack("<Q", cid[:8])[0]
        assert pid in header["entries"], f"{path}: no store entry"
        pkg = c.read_chunk(entry)
        limit = struct.unpack_from("<i", pkg, struct.unpack_from("<I", pkg, 4)[0] + LIMIT_EXPORT_OFFSET)[0]
        print(f"{path}: marker limit = {limit}")

    pak = open(utoc[:-5] + ".pak", "rb").read()
    r = Reader(pak, len(pak) - 160 - 20 - 8 - 8 - 4 - 4)
    assert r.u32() == 0x5A6F12E1 and r.u32() == 11, "bad .pak footer"
    print(".pak footer OK")


if __name__ == "__main__":
    main(sys.argv[1])
