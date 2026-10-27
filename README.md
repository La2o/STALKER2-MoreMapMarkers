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

The limit isn't a `.cfg` setting. It's the `int32` property
`PlayerLandmarksLimitTotal` on the cooked asset
`/Game/GameLite/FPS_Game/UIRemaster/PDA/WorldMap/MapSettingsAsset`.

The asset uses unversioned property serialization, which leaves out any
property that equals the class default. In the current game the limit is at
its default (10), so it isn't in the asset at all. The build adds it to the
property header, inserts the value after the property before it, and updates
the export's size in the export map.

- `tools/iostore.py` is a small reader and writer for the IoStore containers
  the current game uses (TOC v8, container header v4). It reads the game's
  Oodle-compressed containers through `pyooz`. It writes an uncompressed
  container with:
  - BLAKE3 chunk hashes;
  - a perfect-hash chunk lookup table;
  - a directory index and container header;
  - the empty `.pak` that UE needs to mount the container.
- `tools/build.py` finds the asset in the game's containers and checks that
  its properties have the expected layout. It then sets the new limit and
  packs the container.
- `tools/verify.py` reads a container back the way the engine does: chunk
  lookup, hashes, directory, container header and the limit itself.
- `tests/` round-trips a synthetic container: `python -m unittest discover tests`.

## Compatibility

The mod replaces the whole `MapSettingsAsset`, using the copy from the game
version you built it from. Rebuild after a game patch that changes the asset.
The build stops with an error if the asset's properties no longer have the
expected layout. Any other mod that overrides this asset will conflict with
this one.
