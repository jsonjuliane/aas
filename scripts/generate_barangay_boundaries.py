#!/usr/bin/env python3
"""
Generate barangay_boundaries.binan.json from centroids + city geofence (Voronoi cells).

Run from repo root:
  python scripts/generate_barangay_boundaries.py

Polygons are approximate (thesis prototype), clipped to Biñan city boundary.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from shapely.geometry import MultiPoint, Point, mapping, shape
from shapely.ops import voronoi_diagram

from src.config import (
    BARANGAY_CENTROIDS_BINAN_FILE,
    CONFIG_DIR,
    GEOFENCE_BINAN_FILE,
)
from src.routing import _binan_polygon, _load_barangay_centroids


def main() -> int:
    city = _binan_polygon()
    centroids = _load_barangay_centroids()
    points = [Point(clon, clat) for name, clat, clon in centroids]
    names = [name for name, _, _ in centroids]

    # Slight buffer on city so Voronoi ridges on the edge stay inside clip.
    city_buf = city.buffer(0.002)
    vor = voronoi_diagram(MultiPoint(points), envelope=city_buf.envelope)
    if vor.geom_type == "GeometryCollection":
        cells = list(vor.geoms)
    else:
        cells = [vor]

    barangays: list[dict] = []
    for i, (name, clat, clon) in enumerate(centroids):
        pt = Point(clon, clat)
        cell = None
        for g in cells:
            if g.contains(pt) or g.distance(pt) < 1e-9:
                cell = g
                break
        if cell is None and i < len(cells):
            cell = cells[i]
        if cell is None:
            continue
        clipped = cell.intersection(city)
        if clipped.is_empty:
            continue
        geom = clipped
        if geom.geom_type == "MultiPolygon":
            geom = max(geom.geoms, key=lambda p: p.area)
        coords = list(mapping(geom)["coordinates"][0])
        ring = [[float(lon), float(lat)] for lon, lat in coords]
        if ring[0] != ring[-1]:
            ring.append(ring[0])
        barangays.append({"name": name, "boundary": ring})

    out_path = ROOT / CONFIG_DIR / "barangay_boundaries.binan.json"
    payload = {
        "_comment": (
            "Approximate barangay polygons (Voronoi from centroids, clipped to geofence.binan.json). "
            "Regenerate with scripts/generate_barangay_boundaries.py."
        ),
        "version": 1,
        "method": "voronoi_clipped",
        "source_centroids": BARANGAY_CENTROIDS_BINAN_FILE,
        "source_city_boundary": GEOFENCE_BINAN_FILE,
        "barangays": barangays,
    }
    out_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {out_path} ({len(barangays)} barangays)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
