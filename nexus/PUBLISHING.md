# Publishing on Nexus Mods

## Before uploading

- [ ] **In-game test.** Install the 99 version and place more than 10 markers.
      Save, reload, and check the markers are still there.
- [ ] **Build the archives** from your up-to-date game install:
      `pip install -r requirements.txt && python tools/package.py --game "<game folder>"`
      This writes `release/MoreMapMarkers_{50,99,999}-<VERSION>.zip`.

## Mod page fields

| Field | Value |
|---|---|
| Game | S.T.A.L.K.E.R. 2: Heart of Chornobyl |
| Name | More Map Markers |
| Version | contents of `VERSION` |
| Category | User Interface |
| Summary | Raises the PDA's custom map marker limit from 10 to 50, 99 or 999. |
| Description | paste `nexus/description.bbcode` |
| Requirements | none |
| Language | English |
| Tags | UI, Map, Quality of Life |

## Files tab

Upload each zip as a **Main file**:

| File | Name | Description |
|---|---|---|
| `MoreMapMarkers_99-<v>.zip` | More Map Markers 99 | Recommended. 99 custom markers. |
| `MoreMapMarkers_50-<v>.zip` | More Map Markers 50 | 50 custom markers. |
| `MoreMapMarkers_999-<v>.zip` | More Map Markers 999 | 999 custom markers. |

Set the version on every file to the value in `VERSION`.

## Images

Nexus needs at least one image. Use a screenshot of the PDA map with more
than 10 custom markers placed.
