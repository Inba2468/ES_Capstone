OFFLINE MAP TILES
=================

Place your .mbtiles files for offline map support in this directory.

Recommended sources:
  - https://openmaptiles.org/  (free for non-commercial)
  - https://www.maptiler.com/data/  (free tier available)
  - Extract from QGIS using the MBTiles export plugin

For the Chennai / Vengal region:
  Bounding Box: 12.8°N – 13.4°N, 79.9°E – 80.6°E
  Suggested zoom levels: 10–16

Filename example:
  chennai_vengal_z10-16.mbtiles

After placing the file, select it in Settings → Map Source.

If no .mbtiles file is present, the app falls back to OpenStreetMap
tiles (requires internet connection for initial download, then cached).
