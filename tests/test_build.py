"""Round-trip test with a synthetic package: build a "game" container holding a
fake MapSettingsAsset, run the mod build against it, and read the result back.

Run:  python -m unittest discover tests
"""
import os
import struct
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tools"))
import build  # noqa: E402
import verify  # noqa: E402
from iostore import CHUNK_EXPORT_BUNDLE_DATA, Container, chunk_id, write_container  # noqa: E402

MOUNT = "../../../Stalker2/Content/GameLite/FPS_Game/UIRemaster/PDA/WorldMap/"
EXPORT_MAP = 0x28
HEADER_SIZE = EXPORT_MAP + build.EXPORT_ENTRY_SIZE
PACKAGE_TAG = struct.pack("<I", 0x9E2A83C1)

# The property header the game ships (limit left at its default) and the one
# with the limit present, as the game's earlier versions stored it.
VANILLA_FRAGMENTS = bytes.fromhex("010281020104010c02020107")
PATCHED_FRAGMENTS = bytes.fromhex("010281020104010c020b")
ZERO_MASK = b"\x01"


def fake_package(fragments, limit=None):
    values = bytearray(build.VALUES_BEFORE_LIMIT)
    struct.pack_into("<i", values, build.ARRAY_COUNT_OFFSET, build.ARRAY_COUNT)
    if limit is not None:
        values += struct.pack("<i", limit)
    values += b"\xAB" * 20  # properties 18-20
    export = fragments + ZERO_MASK + bytes(values) + b"\0" * 4  # + "no object guid"

    pkg = bytearray(HEADER_SIZE)
    struct.pack_into("<I", pkg, build.SUMMARY_HEADER_SIZE, HEADER_SIZE)
    struct.pack_into("<ii", pkg, build.SUMMARY_EXPORT_MAP, EXPORT_MAP, HEADER_SIZE)
    struct.pack_into("<QQ", pkg, EXPORT_MAP, 0, len(export))
    return bytes(pkg) + export + PACKAGE_TAG


class BuildTest(unittest.TestCase):
    def test_roundtrip(self):
        with tempfile.TemporaryDirectory() as tmp:
            cid = chunk_id(0x8AB7D5BAF8A7251E, CHUNK_EXPORT_BUNDLE_DATA)
            other = chunk_id(0x1234, CHUNK_EXPORT_BUNDLE_DATA)
            entry = ([0x42], [])
            write_container(os.path.join(tmp, "game"), "game", MOUNT,
                            [("MapSettingsAsset.uasset", cid), ("Other.uasset", other)],
                            {cid: (fake_package(VANILLA_FRAGMENTS), entry), other: (b"x" * 300_000, ([], []))})

            source = build.find_asset([os.path.join(tmp, "game.utoc")])
            self.assertIsNotNone(source)
            with source[0]:
                build.build(99, source, os.path.join(tmp, "out"), "Mod_P")

            out = os.path.join(tmp, "out", "Mod_P.utoc")
            verify.main(out)
            with Container(out) as c:
                self.assertEqual(c.chunk_ids.count(cid), 1)
                pkg = c.read_chunk(c.index[cid])
                self.assertEqual(pkg, fake_package(PATCHED_FRAGMENTS, 99))
                self.assertEqual(c.container_header()["entries"][0x8AB7D5BAF8A7251E], entry)

    def test_name_without_direct_perfect_hash(self):
        # This name's container header chunk can't share a 2-slot perfect hash
        # with the asset's chunk unless the container id is salted.
        with tempfile.TemporaryDirectory() as tmp:
            cid = chunk_id(0x8AB7D5BAF8A7251E, CHUNK_EXPORT_BUNDLE_DATA)
            name = "MoreMapMarkers_50_P"
            write_container(os.path.join(tmp, name), name, MOUNT, [("MapSettingsAsset.uasset", cid)],
                            {cid: (fake_package(PATCHED_FRAGMENTS, 50), ([], []))})
            verify.main(os.path.join(tmp, name + ".utoc"))

    def test_inserts_limit(self):
        pkg = build.patch_limit(fake_package(VANILLA_FRAGMENTS), 999, build.VANILLA_LIMIT)
        self.assertEqual(pkg, fake_package(PATCHED_FRAGMENTS, 999))
        self.assertEqual(build.read_limit(pkg), 999)
        # Same place the game's earlier versions stored it.
        self.assertEqual(struct.unpack_from("<i", pkg, HEADER_SIZE + 0x94)[0], 999)

    def test_overwrites_present_limit(self):
        pkg = build.patch_limit(fake_package(PATCHED_FRAGMENTS, 10), 50, build.VANILLA_LIMIT)
        self.assertEqual(pkg, fake_package(PATCHED_FRAGMENTS, 50))

    def test_rejects_unexpected_value(self):
        with self.assertRaises(SystemExit):
            build.patch_limit(fake_package(PATCHED_FRAGMENTS, 7), 99, build.VANILLA_LIMIT)

    def test_rejects_unexpected_layout(self):
        # Property 16 moved to 17: the values before the limit are different.
        with self.assertRaises(SystemExit):
            build.patch_limit(fake_package(bytes.fromhex("010281020104010c03020107")), 99, build.VANILLA_LIMIT)


if __name__ == "__main__":
    unittest.main()
