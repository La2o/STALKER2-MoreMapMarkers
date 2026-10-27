# Updating after a game patch

## 1. Rebuild and verify

```sh
pip install -r requirements.txt
python -m unittest discover tests
python tools/build.py 99 --game "<game folder>"
python tools/verify.py dist/MoreMapMarkers_99_P/MoreMapMarkers_99_P.utoc
```

If this works, test in game and go to step 3. If it fails, the error usually
says which part changed.

## 2. Find what changed

Check these in order. [`FORMAT.md`](FORMAT.md) has the values the tools
expect.

| Error | Likely cause | Where to look |
|---|---|---|
| `skipping <container>: unsupported TOC version`, `unexpected end of data`, `unexpected bytes after the TOC`, `hash mismatch` | The `.utoc` format changed | The version byte at `0x10`, then the chunk meta size |
| `unsupported container header version` | The container header changed | `parse_container_header` in `tools/iostore.py` |
| `MapSettingsAsset not found` (with no `skipping` lines) | The asset moved or was renamed | `ASSET_SUFFIX` in `tools/build.py` |
| `MapSettingsAsset doesn't have the expected layout` | Properties were added or removed | Dump the export's fragments and compare with `FORMAT.md` |
| `Expected the marker limit (10), found ...` | The vanilla limit changed | `VANILLA_LIMIT` in `tools/build.py` |
| `more than one export` | The asset's structure changed | `patch_limit` in `tools/build.py` |

If the property layout changed, decode the new fragments before changing any
offsets: work out which properties are present, then recount the size of the
values before property 17. If the property index itself may have moved,
search the shipping exe for `PlayerLandmarksLimitTotal` again.

Add a test in `tests/test_build.py` for the new layout, and update
`FORMAT.md`.

## 3. Release

1. Test in game: place more than 10 markers, save, reload and check they're
   still there.
2. Bump `VERSION` and add an entry to `CHANGELOG.md`.
3. Build the zips with `python tools/package.py --game "<game folder>"`.
4. On Nexus, use **Update existing file** on each of the three files rather
   than adding new ones. The rest of the checklist is in
   [`nexus/PUBLISHING.md`](../nexus/PUBLISHING.md).
