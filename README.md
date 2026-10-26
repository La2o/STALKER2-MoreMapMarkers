# STALKER2-MoreMapMarkers

Raises the number of custom markers you can place on the PDA map in
S.T.A.L.K.E.R. 2: Heart of Chornobyl. The vanilla limit is 10.

Made for this [Nexus mod request](https://forums.nexusmods.com/topic/13502974-mod-request-stalker-2-more-player-markers-on-map/).

The repository has no game files in it. The build script reads the asset from
your own install, changes one number, and writes the mod.

## Build

You need Python 3.9 or newer.

```sh
pip install -r requirements.txt
python tools/build.py 99 --game "C:/Program Files (x86)/Steam/steamapps/common/S.T.A.L.K.E.R. 2 Heart of Chornobyl"
python tools/verify.py dist/MoreMapMarkers_99_P/MoreMapMarkers_99_P.utoc
```

`--game` is the folder that contains `Stalker2`. The output goes to
`dist/MoreMapMarkers_99_P/`.

## Install

1. Copy the three built files (`.pak`, `.utoc`, `.ucas`) to
   `<game>/Stalker2/Content/Paks/~mods/`. Create `~mods` if it isn't there.
2. Install only one limit at a time.

99 is a good default, because it still fits the PDA's marker counter.

To uninstall, delete the three files.

## Release

`python tools/package.py --game "<game folder>"` writes the Nexus upload zips
(50, 99 and 999) to `release/`. The publishing checklist is in
[`nexus/PUBLISHING.md`](nexus/PUBLISHING.md).

## How it works

The limit isn't a `.cfg` setting. It's an `int32` property on the cooked asset
`/Game/GameLite/FPS_Game/UIRemaster/PDA/WorldMap/MapSettingsAsset`, at offset
`0x94` into the package's export data.

- `tools/iostore.py` is a small reader and writer for UE 5.1 IoStore
  containers (TOC v5, container header v2). It reads the game's
  Oodle-compressed containers through `pyooz`. It writes an uncompressed
  container with:
  - BLAKE3 chunk hashes;
  - a perfect-hash chunk lookup table;
  - a directory index and container header;
  - the empty `.pak` that UE needs to mount the container.
- `tools/build.py` finds the asset in the game's containers and checks that
  the field holds the vanilla value (10). It then writes the new limit and
  packs the container.
- `tools/verify.py` reads a container back the way the engine does: chunk
  lookup, hashes, directory, container header and the limit itself.
- `tests/` round-trips a synthetic container: `python -m unittest discover tests`.

## Compatibility

The mod replaces the whole `MapSettingsAsset`, using the copy from the game
version you built it from. Rebuild after a game patch that changes the asset.
The build stops with an error if the field no longer holds 10 at the expected
offset. Any other mod that overrides this asset will conflict with this one.
