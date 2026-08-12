#!/usr/bin/env python3
"""Offline building-footprint detector over Esri World Imagery.

Runs OUTSIDE the API (heavy CV/ML should never block a web worker). It fetches
Esri World Imagery tiles for a bounding box, detects candidate rooftops, and
writes a GeoJSON FeatureCollection in EPSG:4326. Feed that file to the app's
"Detected footprints" import, which dedupes it against the register and imports
only the new rooftops — tagged pilot-only.

LICENCE: Esri World Imagery is display-only here. Footprints derived from it are
a derivative work and are NOT commercially usable until re-sourced (re-detected
over your own drone orthomosaic, or field-confirmed). The app tags them
accordingly; this tool only produces candidates.

The detector is deliberately pluggable. The default is a light OpenCV baseline —
useful for finding obvious new rooftops in stale areas, but rough on dense or
same-coloured roofs. For production, swap `detect_footprints` for a real
segmentation model (e.g. a U-Net / Mask R-CNN / SAM-geo ONNX model) — or, best,
run detection on a georeferenced drone orthomosaic instead of Esri.

Usage:
    python detect_buildings.py --bbox "MINLON,MINLAT,MAXLON,MAXLAT" \
        --zoom 19 --out candidates.geojson
    # Wuye District approx bbox: 7.418,9.030,7.452,9.060

Requires (install on your machine, not the API):
    pip install requests numpy opencv-python-headless pillow
"""
from __future__ import annotations

import argparse
import json
import math
import sys

TILE = 256
ESRI = ("https://server.arcgisonline.com/ArcGIS/rest/services/"
        "World_Imagery/MapServer/tile/{z}/{y}/{x}")


# --- Web-Mercator tile <-> lon/lat (EPSG:4326) ------------------------------

def lonlat_to_tile(lon: float, lat: float, z: int) -> tuple[float, float]:
    n = 2 ** z
    x = (lon + 180.0) / 360.0 * n
    lat_r = math.radians(lat)
    y = (1.0 - math.asinh(math.tan(lat_r)) / math.pi) / 2.0 * n
    return x, y


def pixel_to_lonlat(tx: int, ty: int, z: int, px: float, py: float) -> tuple[float, float]:
    """Global pixel (tile tx,ty + in-tile px,py) -> lon/lat."""
    n = 2 ** z
    lon = (tx + px / TILE) / n * 360.0 - 180.0
    lat_r = math.atan(math.sinh(math.pi * (1.0 - 2.0 * (ty + py / TILE) / n)))
    return lon, math.degrees(lat_r)


def tile_range(bbox: tuple[float, float, float, float], z: int):
    minlon, minlat, maxlon, maxlat = bbox
    x0, y1 = lonlat_to_tile(minlon, minlat, z)   # minlat -> larger y
    x1, y0 = lonlat_to_tile(maxlon, maxlat, z)
    return (int(math.floor(min(x0, x1))), int(math.floor(min(y0, y1))),
            int(math.floor(max(x0, x1))), int(math.floor(max(y0, y1))))


# --- Detector (pluggable) ---------------------------------------------------

def detect_footprints(img_bgr, min_px: int, max_px: int,
                      veg_exg: float = 18.0, max_circularity: float = 0.82,
                      max_veg_fraction: float = 0.35):
    """Return a list of pixel-space polygons (Nx2 arrays) for one tile image.

    Baseline: segment bright, compact blobs, but reject vegetation. Trees and
    shrubs are the baseline's worst false positive — they read as round green
    blobs — so we (1) mask out vegetation using Excess-Green (2G-R-B) before
    thresholding, (2) drop candidates that are mostly vegetation, and (3) drop
    near-circular blobs (a tree canopy is round; a building rarely is). Replace
    this function with a trained segmentation model for real accuracy — same
    signature.
    """
    import cv2
    import numpy as np

    b, g, r = cv2.split(img_bgr.astype(np.float32))
    exg = 2.0 * g - r - b                       # high on green vegetation
    veg = (exg > veg_exg).astype(np.uint8) * 255
    veg = cv2.dilate(veg, np.ones((3, 3), np.uint8))

    gray = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2GRAY)
    gray = cv2.bilateralFilter(gray, 7, 50, 50)
    # Bright rooftops (metal/zinc) stand out; adaptive keeps it local to shading.
    th = cv2.adaptiveThreshold(gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                               cv2.THRESH_BINARY, 51, -8)
    th = cv2.bitwise_and(th, cv2.bitwise_not(veg))       # remove vegetation
    th = cv2.morphologyEx(th, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))
    th = cv2.morphologyEx(th, cv2.MORPH_CLOSE, np.ones((5, 5), np.uint8))
    contours, _ = cv2.findContours(th, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    polys = []
    for c in contours:
        area = cv2.contourArea(c)
        if area < min_px or area > max_px:
            continue
        peri = cv2.arcLength(c, True)
        if peri <= 0:
            continue
        # Roundness: 1.0 = perfect circle (a tree); buildings are lower.
        circularity = 4.0 * np.pi * area / (peri * peri)
        if circularity > max_circularity:
            continue
        approx = cv2.approxPolyDP(c, 0.02 * peri, True)
        if len(approx) < 4:
            continue
        # Reject thin/road-like shapes: require a decent fill of its bbox.
        x, y, w, h = cv2.boundingRect(approx)
        if w == 0 or h == 0 or area / float(w * h) < 0.45:
            continue
        # Reject blobs that are mostly vegetation.
        mask = np.zeros(veg.shape, np.uint8)
        cv2.drawContours(mask, [c], -1, 255, -1)
        inside = cv2.countNonZero(mask)
        if inside > 0 and cv2.countNonZero(cv2.bitwise_and(mask, veg)) / inside > max_veg_fraction:
            continue
        polys.append(approx.reshape(-1, 2).astype(float))
    return polys


# --- Driver -----------------------------------------------------------------

def run(bbox, zoom, out_path, min_m2, max_m2):
    import cv2
    import numpy as np
    import requests

    x_min, y_min, x_max, y_max = tile_range(bbox, zoom)
    n_tiles = (x_max - x_min + 1) * (y_max - y_min + 1)
    if n_tiles > 4000:
        sys.exit(f"{n_tiles} tiles at z{zoom} is a lot — narrow the bbox or "
                 "lower the zoom.")
    # Approx ground resolution (m/px) at this latitude, for area thresholds.
    lat0 = (bbox[1] + bbox[3]) / 2.0
    mpp = 156543.03392 * math.cos(math.radians(lat0)) / (2 ** zoom)
    min_px = max(4.0, min_m2 / (mpp * mpp))
    max_px = max_m2 / (mpp * mpp)

    features = []
    sess = requests.Session()
    sess.headers["User-Agent"] = "aviva-geoplan-detector/1.0"
    done = 0
    for tx in range(x_min, x_max + 1):
        for ty in range(y_min, y_max + 1):
            done += 1
            url = ESRI.format(z=zoom, x=tx, y=ty)
            try:
                r = sess.get(url, timeout=30)
                r.raise_for_status()
                arr = np.frombuffer(r.content, np.uint8)
                img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
                if img is None:
                    continue
            except Exception as exc:                       # noqa: BLE001
                print(f"  tile {tx},{ty} failed: {exc}", file=sys.stderr)
                continue
            for poly in detect_footprints(img, min_px, max_px):
                ring = [list(pixel_to_lonlat(tx, ty, zoom, px, py))
                        for px, py in poly]
                ring.append(ring[0])
                features.append({
                    "type": "Feature",
                    "geometry": {"type": "Polygon", "coordinates": [ring]},
                    "properties": {"source": "esri_detection", "confidence": 0.5,
                                   "zoom": zoom}})
            if done % 50 == 0:
                print(f"  {done}/{n_tiles} tiles, {len(features)} candidates…",
                      file=sys.stderr)

    fc = {"type": "FeatureCollection",
          "properties": {"source": "Esri World Imagery (display-only)",
                         "detector": "opencv-baseline", "zoom": zoom,
                         "note": "Pilot-only; re-source before commercial use."},
          "features": features}
    with open(out_path, "w") as fh:
        json.dump(fc, fh)
    print(f"Wrote {len(features)} candidate footprints to {out_path}")


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--bbox", required=True,
                    help="minlon,minlat,maxlon,maxlat (EPSG:4326)")
    ap.add_argument("--zoom", type=int, default=19)
    ap.add_argument("--out", default="candidates.geojson")
    ap.add_argument("--min-m2", type=float, default=8.0)
    ap.add_argument("--max-m2", type=float, default=2000.0)
    args = ap.parse_args()
    bbox = tuple(float(v) for v in args.bbox.split(","))
    if len(bbox) != 4:
        ap.error("--bbox needs 4 comma-separated numbers")
    run(bbox, args.zoom, args.out, args.min_m2, args.max_m2)


if __name__ == "__main__":
    main()
