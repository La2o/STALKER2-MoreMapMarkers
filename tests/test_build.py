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
HEADER_SIZE = 0x40


def fake_package(limit):
    pkg = bytearray(HEADER_SIZE + build.LIMIT_EXPORT_OFFSET + 16)
    struct.pack_into("<I", pkg, 4, HEADER_SIZE)
    struct.pack_into("<i", pkg, HEADER_SIZE + build.LIMIT_EXPORT_OFFSET, limit)
    return bytes(pkg)


class BuildTest(unittest.TestCase):
    def test_roundtrip(self):
        with tempfile.TemporaryDirectory() as tmp:
            cid = chunk_id(0x8AB7D5BAF8A7251E, CHUNK_EXPORT_BUNDLE_DATA)
            other = chunk_id(0x1234, CHUNK_EXPORT_BUNDLE_DATA)
            entry = (1, 1, [0x42], [])
            write_container(os.path.join(tmp, "game"), "game", MOUNT,
                            [("MapSettingsAsset.uasset", cid), ("Other.uasset", other)],
                            {cid: (fake_package(10), entry), other: (b"x" * 300_000, (1, 1, [], []))})

            source = build.find_asset([os.path.join(tmp, "game.utoc")])
            self.assertIsNotNone(source)
            build.build(99, source, os.path.join(tmp, "out"), "Mod_P")

            out = os.path.join(tmp, "out", "Mod_P.utoc")
            verify.main(out)
            c = Container(out)
            self.assertEqual(c.chunk_ids.count(cid), 1)
            pkg = c.read_chunk(c.index[cid])
            self.assertEqual(pkg, fake_package(99))
            self.assertEqual(c.container_header()["entries"][0x8AB7D5BAF8A7251E], entry)

    def test_rejects_unexpected_value(self):
        with self.assertRaises(SystemExit):
            build.patch_limit(fake_package(7), 99, build.VANILLA_LIMIT)


if __name__ == "__main__":
    unittest.main()
