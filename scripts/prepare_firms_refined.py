"""Create the province-based VIIRS fire-source dataset for the 2019 case study.

The primary source region is the union of Riau, Jambi, and Sumatera Selatan.
The previous rectangular subset is retained separately as a sensitivity dataset.
This script uses only pandas/numpy plus Python's standard library.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd


PROVINCES = ("Riau", "Jambi", "Sumatera Selatan")
PROVINCE_SLUGS = {
    "Riau": "riau",
    "Jambi": "jambi",
    "Sumatera Selatan": "south_sumatra",
}


def points_in_ring(x: np.ndarray, y: np.ndarray, ring: list[list[float]]) -> np.ndarray:
    """Return a ray-casting point-in-polygon mask for one closed GeoJSON ring."""
    vertices = np.asarray(ring, dtype=float)
    inside = np.zeros(x.shape, dtype=bool)
    xj, yj = vertices[-1]

    for xi, yi in vertices:
        crosses = (yi > y) != (yj > y)
        intersection_x = (xj - xi) * (y - yi) / ((yj - yi) + 1e-300) + xi
        inside ^= crosses & (x < intersection_x)
        xj, yj = xi, yi

    return inside


def points_in_polygon(x: np.ndarray, y: np.ndarray, rings: list) -> np.ndarray:
    """Test an exterior ring and remove any interior holes."""
    result = points_in_ring(x, y, rings[0])
    for hole in rings[1:]:
        result &= ~points_in_ring(x, y, hole)
    return result


def points_in_geometry(x: np.ndarray, y: np.ndarray, geometry: dict) -> np.ndarray:
    """Test points against a GeoJSON Polygon or MultiPolygon."""
    result = np.zeros(x.shape, dtype=bool)
    polygons = (
        [geometry["coordinates"]]
        if geometry["type"] == "Polygon"
        else geometry["coordinates"]
    )

    for rings in polygons:
        exterior = np.asarray(rings[0], dtype=float)
        xmin, ymin = exterior.min(axis=0)
        xmax, ymax = exterior.max(axis=0)
        candidates = (x >= xmin) & (x <= xmax) & (y >= ymin) & (y <= ymax)
        if not candidates.any():
            continue
        candidate_indices = np.flatnonzero(candidates)
        contained = points_in_polygon(x[candidates], y[candidates], rings)
        result[candidate_indices[contained]] = True

    return result


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--input",
        default="data/raw/firms/viirs-snpp_2019_Indonesia.csv",
    )
    parser.add_argument(
        "--boundary",
        default="data/raw/boundaries/indonesia_provinces_2025.geojson",
    )
    parser.add_argument(
        "--subset",
        default="data/processed/viirs_snpp_riau_jambi_south_sumatra_2019-08-01_2019-09-30.csv",
    )
    parser.add_argument(
        "--daily",
        default="data/processed/viirs_snpp_riau_jambi_south_sumatra_daily_2019-08-01_2019-09-30.csv",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    with Path(args.boundary).open(encoding="utf-8") as boundary_file:
        boundary = json.load(boundary_file)

    features = {
        feature["properties"]["name"]: feature
        for feature in boundary["features"]
        if feature["properties"].get("name") in PROVINCES
    }
    missing = set(PROVINCES) - set(features)
    if missing:
        raise ValueError(f"Boundary file is missing provinces: {sorted(missing)}")

    fires = pd.read_csv(args.input, dtype={"confidence": "string"})
    dates = pd.to_datetime(fires["acq_date"], format="%Y-%m-%d", errors="raise")
    fires = fires.loc[
        dates.between("2019-08-01", "2019-09-30")
        & fires["latitude"].between(-6.0, 3.5)
        & fires["longitude"].between(98.0, 106.5)
    ].copy()

    x = fires["longitude"].to_numpy(dtype=float)
    y = fires["latitude"].to_numpy(dtype=float)
    fires["source_province"] = pd.NA

    for province in PROVINCES:
        mask = points_in_geometry(x, y, features[province]["geometry"])
        fires.loc[mask, "source_province"] = province

    fires = fires.loc[fires["source_province"].notna()].copy()
    fires.to_csv(args.subset, index=False, date_format="%Y-%m-%d")

    vegetation = fires["type"].eq(0)
    eligible = vegetation & fires["confidence"].isin(["n", "h"])
    fires["eligible_frp_mw"] = fires["frp"].where(eligible, 0.0)
    fires["eligible_detection"] = eligible.astype(int)

    daily = fires.groupby("acq_date", sort=True).agg(
        detection_count=("latitude", "size"),
        presumed_vegetation_fire_count=("type", lambda values: values.eq(0).sum()),
        low_confidence_count=("confidence", lambda values: values.eq("l").sum()),
        nominal_confidence_count=("confidence", lambda values: values.eq("n").sum()),
        high_confidence_count=("confidence", lambda values: values.eq("h").sum()),
        total_frp_mw=("frp", "sum"),
        analysis_eligible_count=("eligible_detection", "sum"),
        analysis_eligible_frp_mw=("eligible_frp_mw", "sum"),
    )

    for province in PROVINCES:
        province_rows = fires.loc[fires["source_province"].eq(province)]
        province_daily = province_rows.groupby("acq_date").agg(
            eligible_count=("eligible_detection", "sum"),
            eligible_frp_mw=("eligible_frp_mw", "sum"),
        )
        slug = PROVINCE_SLUGS[province]
        daily[f"{slug}_eligible_count"] = province_daily["eligible_count"]
        daily[f"{slug}_eligible_frp_mw"] = province_daily["eligible_frp_mw"]

    daily = daily.fillna(0).reset_index().rename(columns={"acq_date": "date"})
    count_columns = [column for column in daily if column.endswith("count")]
    daily[count_columns] = daily[count_columns].astype(int)
    frp_columns = [column for column in daily if column.endswith("frp_mw")]
    daily[frp_columns] = daily[frp_columns].round(3)
    daily.to_csv(args.daily, index=False)

    print(f"Source provinces: {', '.join(PROVINCES)}")
    print(f"Subset rows: {len(fires):,}")
    print(f"Eligible detections: {int(eligible.loc[fires.index].sum()):,}")
    print(f"Subset: {args.subset}")
    print(f"Daily summary: {args.daily}")


if __name__ == "__main__":
    main()
