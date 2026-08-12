# Building auto-detection (offline)

`detect_buildings.py` finds candidate rooftops in Esri World Imagery and writes
a GeoJSON file. The Aviva GeoPlan app then imports it — deduping against the
existing register and keeping only genuinely new footprints.

## Why it's offline

Detection is CPU/ML-heavy and must not run inside the API (one request would tie
up a worker for minutes). You run this on your own machine, then upload the
result in the app.

## Licence — important

Esri World Imagery is **display-only** in this project. Footprints detected from
it are a derivative work and are **not commercially usable** until re-sourced
(re-detected over your own drone orthomosaic, or field-confirmed). The app tags
every imported detection as `desk_reference_restricted` (pilot-only), exactly as
it does a hand-trace over the same imagery. Detections are **rooftops, not
premises** — they carry no unit count.

## Setup (one command, on your Mac — not the API container)

```
bash tools/setup.sh
```

This creates a native venv in `tools/.venv`, installs the core deps
(`requirements.txt`: requests, numpy, opencv-python-headless), verifies OpenCV,
and makes `tools/outputs/`. It's isolated from the FastAPI backend, which runs in
Docker with its own Python — so AI deps never touch the web app.

Optional extras for later detectors / GIS post-processing (not needed here):

```
source tools/.venv/bin/activate
pip install -r tools/requirements-extra.txt
```

## Run

```
cd tools
source .venv/bin/activate
python detect_buildings.py \
  --bbox "7.418,9.030,7.452,9.060" \   # Wuye approx (minlon,minlat,maxlon,maxlat)
  --zoom 18 \                          # ~600 tiles; use 19 (~2,250 tiles) for finer detail
  --out outputs/candidates.geojson
```

Tile counts for this bbox: z17 ≈ 168, z18 ≈ 598, z19 ≈ 2,250 (the script caps at
4,000). `--min-m2` / `--max-m2` filter implausible footprints. The bbox is a
rough Wuye box; the app clips to your real boundary on import, so anything
outside is discarded automatically.

## Import into the app

Projects → Wuye District → Import → **Detected footprints (GeoJSON)** → choose
`candidates.geojson`. The app reports how many were imported vs. skipped as
duplicates or out-of-boundary, then draws the new buildings (pilot-only tag).

## Detector quality & the production path

The default detector is a light OpenCV baseline: good for spotting obvious new
rooftops in stale areas, rough on dense or same-coloured roofs. For production,
replace `detect_footprints()` with a trained segmentation model (same signature)
— or, best, run detection on a georeferenced **drone orthomosaic**, which is both
more accurate and free of the imagery licence restriction.
