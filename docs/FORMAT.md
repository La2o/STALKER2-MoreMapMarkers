# File format notes

What the tools rely on, for the game version the mod was built against
(October 2026). If a game patch breaks the build, compare against this first.

## IoStore container (`.utoc` / `.ucas`)

`tools/iostore.py` reads and writes these.

- **TOC version 8** (`ReplaceIoChunkHashWithIoHash`). The version byte is at
  offset `0x10` of the `.utoc`.
- **Chunk metas are 24 bytes**: a 20-byte BLAKE3 hash (`FIoHash`), one flags
  byte and 3 padding bytes. The writer emits the hash plus 4 zero bytes.
- **Chunk lookup** uses a perfect hash, a variant of FNV-1a. With only 2
  slots the slot is a single parity bit that no seed can change, so
  `write_container` salts the container id (`name#salt`) until a perfect hash
  exists. The seed search stops at 100,000.
- The game's containers are Oodle-compressed and are read through `pyooz`.
  The mod's container is written uncompressed.
- UE needs an empty companion `.pak` with the same name to mount the
  container.

## Container header

- **Version 4** (`SoftPackageReferences`).
- **Store entries are 16 bytes**: an imports array and a shader map array.
  There's no export info, which was removed in version 3.
- After the store come 6 zero `u32`s: optional segment ids, the optional
  store, the redirects name map count, localized packages, package redirects
  and `bContainsSoftPackageReferences`.

## Zen package summary

| Offset | Field |
|---|---|
| `0x04` | header size, which is also where the export data starts |
| `0x20` | `ExportMapOffset` |
| `0x24` | `ExportBundleEntriesOffset` |

- `FExportMapEntry` is 72 bytes, with `CookedSerialSize` at `+8`.
- The export data ends with the 4-byte package tag `0x9E2A83C1`.
  `tools/verify.py` checks that export start + serial size + 4 equals the
  package length.

## The asset

`/Game/GameLite/FPS_Game/UIRemaster/PDA/WorldMap/MapSettingsAsset`, package id
`0x8AB7D5BAF8A7251E`, in `pakchunk16-Windows.utoc`. It has exactly one export.

The export uses **unversioned property serialization**:

1. A list of `u16` fragments. Bits 0–6 are the number of properties to skip,
   bit 7 means a zero mask follows, bit 8 marks the last fragment, and bits
   9 and up are the number of properties present.
2. An optional zero mask.
3. The values of the present properties, in order.

Properties equal to the class default are left out entirely.

### The limit

- Name: `PlayerLandmarksLimitTotal`, found by scanning
  `Stalker2-Win64-Shipping.exe` for marker strings.
- Property index **17**, an `int32`. Vanilla value: **10**.
- In the current game it equals the class default, so **it isn't in the
  asset**, and the build inserts it.

| | Fragments | Zero mask |
|---|---|---|
| Vanilla | `010281020104010c02020107` | `01` |
| Patched | `010281020104010c020b` | none |

- The properties before the limit are 1, 3, 5, 6, 8–13 and 16. Their values
  take `0x89` bytes, so the limit goes at values start + `0x89`.
- Property 16 is an array of 5 structs. Its count sits at values start +
  `0x21`, and the build checks it as a sanity check on the layout.
- After inserting, the build adds 4 to the export's `CookedSerialSize`.
- If a future version stores the limit, the build checks it equals 10 and
  overwrites it in place.

## History

- **Patch 1.x and earlier:** TOC v5, container header v2, and the limit was
  stored at a fixed offset (`0x94` from the export start).
- **October 2026 (~2.1):** all three changed at once, to what's described
  above.
