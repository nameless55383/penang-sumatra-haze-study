"""Parse NOAA HYSPLIT endpoints, test province intersections, and draw event maps."""

from __future__ import annotations

import csv
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import pandas as pd
from PIL import Image, ImageDraw, ImageFont

from prepare_firms_refined import points_in_geometry


ROOT = Path(__file__).resolve().parents[1]
BOUNDARY = ROOT / "data/raw/boundaries/indonesia_provinces_2025.geojson"
FIRES = ROOT / "data/processed/viirs_snpp_riau_jambi_south_sumatra_2019-08-01_2019-09-30.csv"
JOINED = ROOT / "data/processed/penang_sumatra_daily_joined_2019-08-01_2019-09-30.csv"
OUTPUT_DIR = ROOT / "outputs/maps"
SUMMARY_FILE = ROOT / "data/processed/hysplit_province_intersections_2019.csv"
ENSEMBLE_SUMMARY_FILE = ROOT / "data/processed/hysplit_ensemble_member_intersections_2019-09-22.csv"

ENSEMBLE = {
    "event_date": "2019-09-22",
    "arrival": "2019-09-21 18:00 UTC (22 Sep 02:00 MYT)",
    "arrival_height_m_agl": 1500,
    "tdump": ROOT / "outputs/hysplit/2019-09-22-ensemble-1500m/tdump_ensemble_2019-09-21_18UTC_1500m.txt",
    "job": "179130",
}

EVENTS = [
    {
        "event_date": "2019-08-11",
        "arrival": "2019-08-11 06:00 UTC",
        "tdump": ROOT / "outputs/hysplit/2019-08-11/tdump_2019-08-11_06UTC.txt",
        "output": OUTPUT_DIR / "hysplit_control_2019-08-11.png",
        "job": "178849",
        "case_type": "low-AOD control",
    },
    {
        "event_date": "2019-09-11",
        "arrival": "2019-09-11 06:00 UTC",
        "tdump": ROOT / "outputs/hysplit/2019-09-11/tdump_2019-09-11_06UTC.txt",
        "output": OUTPUT_DIR / "hysplit_event_2019-09-11.png",
        "job": "163615",
        "case_type": "high-AOD event",
    },
    {
        "event_date": "2019-09-22",
        "arrival": "2019-09-21 18:00 UTC (22 Sep 02:00 MYT)",
        "tdump": ROOT / "outputs/hysplit/2019-09-22/tdump_2019-09-21_18UTC.txt",
        "output": OUTPUT_DIR / "hysplit_event_2019-09-22.png",
        "job": "163662",
        "case_type": "high-AOD event",
    },
]

PROVINCES = ["Riau", "Jambi", "Sumatera Selatan"]
PROVINCE_COLORS = {
    "Riau": (59, 130, 246),
    "Jambi": (245, 158, 11),
    "Sumatera Selatan": (239, 68, 68),
}
HEIGHT_COLORS = {500: (0, 140, 90), 1500: (230, 126, 34), 3000: (125, 73, 180)}

WIDTH, HEIGHT = 1800, 1250
LEFT, TOP, RIGHT, BOTTOM = 135, 165, 70, 150
LON_MIN, LON_MAX = 95.0, 111.0
LAT_MIN, LAT_MAX = -7.0, 7.0


def font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    filename = "arialbd.ttf" if bold else "arial.ttf"
    return ImageFont.truetype(f"C:/Windows/Fonts/{filename}", size)


def xy(lon: float, lat: float) -> tuple[int, int]:
    plot_width = WIDTH - LEFT - RIGHT
    plot_height = HEIGHT - TOP - BOTTOM
    x = LEFT + (lon - LON_MIN) / (LON_MAX - LON_MIN) * plot_width
    y = TOP + (LAT_MAX - lat) / (LAT_MAX - LAT_MIN) * plot_height
    return round(x), round(y)


def polygon_parts(geometry: dict) -> list:
    return [geometry["coordinates"]] if geometry["type"] == "Polygon" else geometry["coordinates"]


def parse_tdump(path: Path) -> pd.DataFrame:
    lines = path.read_text(encoding="utf-8").splitlines()
    start = next(i for i, line in enumerate(lines) if "PRESSURE" in line) + 1
    records = []
    for line in lines[start:]:
        fields = line.split()
        if len(fields) < 13:
            continue
        records.append(
            {
                "trajectory": int(fields[0]),
                "year": 2000 + int(fields[2]),
                "month": int(fields[3]),
                "day": int(fields[4]),
                "hour": int(fields[5]),
                "age_hours": float(fields[8]),
                "latitude": float(fields[9]),
                "longitude": float(fields[10]),
                "height_m_agl": float(fields[11]),
                "pressure_hpa": float(fields[12]),
            }
        )
    data = pd.DataFrame(records)
    data["time_utc"] = pd.to_datetime(data[["year", "month", "day", "hour"]], utc=True)
    arrival_heights = data.loc[data["age_hours"].eq(0)].set_index("trajectory")["height_m_agl"]
    data["arrival_height_m_agl"] = data["trajectory"].map(arrival_heights).round().astype(int)
    return data


def add_province_membership(data: pd.DataFrame, boundary_features: dict[str, dict]) -> pd.DataFrame:
    result = data.copy()
    result["source_province"] = ""
    x = result["longitude"].to_numpy()
    y = result["latitude"].to_numpy()
    for province in PROVINCES:
        mask = points_in_geometry(x, y, boundary_features[province]["geometry"])
        result.loc[mask, "source_province"] = province
    return result


def draw_event(event: dict, data: pd.DataFrame, boundaries: dict, fires: pd.DataFrame, daily: pd.Series) -> None:
    image = Image.new("RGB", (WIDTH, HEIGHT), "white")
    draw = ImageDraw.Draw(image)

    for lon in range(96, 111, 2):
        x, _ = xy(lon, LAT_MIN)
        draw.line((x, TOP, x, HEIGHT - BOTTOM), fill=(222, 227, 234), width=1)
        draw.text((x, HEIGHT - BOTTOM + 16), f"{lon}°E", font=font(20), fill=(65, 74, 88), anchor="ma")
    for lat in range(-6, 8, 2):
        _, y = xy(LON_MIN, lat)
        draw.line((LEFT, y, WIDTH - RIGHT, y), fill=(222, 227, 234), width=1)
        label = f"{abs(lat)}°{'N' if lat > 0 else 'S' if lat < 0 else ''}"
        draw.text((LEFT - 14, y), label, font=font(20), fill=(65, 74, 88), anchor="rm")

    overlay = Image.new("RGBA", image.size, (0, 0, 0, 0))
    overlay_draw = ImageDraw.Draw(overlay)
    for feature in boundaries["features"]:
        name = feature["properties"].get("name")
        fill = PROVINCE_COLORS.get(name)
        for rings in polygon_parts(feature["geometry"]):
            exterior = [xy(lon, lat) for lon, lat in rings[0]]
            if fill:
                overlay_draw.polygon(exterior, fill=(*fill, 45), outline=(*fill, 230), width=3)
            else:
                overlay_draw.line(exterior + [exterior[0]], fill=(145, 152, 164, 140), width=1)
    image = Image.alpha_composite(image.convert("RGBA"), overlay)

    draw = ImageDraw.Draw(image)
    event_date = datetime.strptime(event["event_date"], "%Y-%m-%d").replace(tzinfo=timezone.utc)
    fire_start = (event_date - timedelta(days=2)).date().isoformat()
    event_fires = fires.loc[fires["acq_date"].between(fire_start, event["event_date"])].iloc[::3]
    for row in event_fires.itertuples():
        px, py = xy(float(row.longitude), float(row.latitude))
        draw.ellipse((px - 2, py - 2, px + 2, py + 2), fill=(198, 40, 40, 145))

    for trajectory, group in data.groupby("trajectory"):
        group = group.sort_values("age_hours")
        height = int(group["arrival_height_m_agl"].iloc[0])
        color = HEIGHT_COLORS[height]
        points = [xy(lon, lat) for lon, lat in zip(group["longitude"], group["latitude"])]
        draw.line(points, fill=(*color, 255), width=6, joint="curve")
        for row in group.loc[group["age_hours"].mod(12).eq(0)].itertuples():
            px, py = xy(row.longitude, row.latitude)
            draw.ellipse((px - 6, py - 6, px + 6, py + 6), fill=(*color, 255), outline=(255, 255, 255, 255), width=2)

    gx, gy = xy(100.329, 5.414)
    draw.regular_polygon((gx, gy, 14), n_sides=5, rotation=-18, fill=(15, 23, 42, 255))
    draw.text((gx + 22, gy), "George Town", font=font(23, True), fill=(15, 23, 42), anchor="lm")

    draw.rectangle((LEFT, TOP, WIDTH - RIGHT, HEIGHT - BOTTOM), outline=(30, 41, 59), width=3)
    draw.text((WIDTH // 2, 45), f"HYSPLIT back trajectories: {event['event_date']} ({event['case_type']})", font=font(36, True), fill=(23, 32, 51), anchor="ma")
    subtitle = f"Arrival {event['arrival']} • GDAS1 • 72 h • NOAA job {event['job']}"
    draw.text((WIDTH // 2, 96), subtitle, font=font(24), fill=(60, 69, 82), anchor="ma")
    evidence = (
        f"George Town AOD {float(daily['aod_055_mean']):.3f}  |  fires {int(float(daily['analysis_eligible_count'])):,}  |  "
        f"source→Penang 850 hPa {float(daily['source_toward_penang850_mps']):.2f} m/s"
    )
    draw.text((WIDTH // 2, 132), evidence, font=font(22), fill=(60, 69, 82), anchor="ma")

    legend_x, legend_y = LEFT + 22, HEIGHT - BOTTOM - 205
    draw.rounded_rectangle((legend_x, legend_y, legend_x + 550, legend_y + 180), radius=12, fill=(255, 255, 255, 238), outline=(120, 128, 140), width=2)
    for index, height in enumerate((500, 1500, 3000)):
        y = legend_y + 30 + index * 42
        color = HEIGHT_COLORS[height]
        draw.line((legend_x + 20, y, legend_x + 85, y), fill=(*color, 255), width=6)
        draw.text((legend_x + 100, y), f"{height:,} m arrival trajectory", font=font(21), fill=(35, 42, 54), anchor="lm")
    draw.ellipse((legend_x + 320, legend_y + 20, legend_x + 328, legend_y + 28), fill=(198, 40, 40, 180))
    draw.text((legend_x + 342, legend_y + 25), "eligible fires, prior 2 days", font=font(20), fill=(45, 50, 60), anchor="lm")

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    image.convert("RGB").save(event["output"], quality=95)


def main() -> None:
    with BOUNDARY.open(encoding="utf-8") as source:
        boundaries = json.load(source)
    boundary_features = {feature["properties"].get("name"): feature for feature in boundaries["features"]}
    fires = pd.read_csv(FIRES)
    fires = fires.loc[fires["type"].eq(0) & fires["confidence"].isin(["n", "h"])]
    joined = pd.read_csv(JOINED).set_index("date")

    summary_rows = []
    for event in EVENTS:
        data = add_province_membership(parse_tdump(event["tdump"]), boundary_features)
        draw_event(event, data, boundaries, fires, joined.loc[event["event_date"]])
        for trajectory, group in data.groupby("trajectory"):
            height = int(group["arrival_height_m_agl"].iloc[0])
            for province in PROVINCES:
                province_rows = group.loc[group["source_province"].eq(province)]
                summary_rows.append(
                    {
                        "event_date": event["event_date"],
                        "arrival": event["arrival"],
                        "noaa_job": event["job"],
                        "case_type": event["case_type"],
                        "arrival_height_m_agl": height,
                        "province": province,
                        "hourly_endpoints_inside": len(province_rows),
                        "oldest_age_inside_hours": province_rows["age_hours"].min() if len(province_rows) else "",
                        "youngest_age_inside_hours": province_rows["age_hours"].max() if len(province_rows) else "",
                    }
                )

    SUMMARY_FILE.parent.mkdir(parents=True, exist_ok=True)
    with SUMMARY_FILE.open("w", newline="", encoding="utf-8") as target:
        writer = csv.DictWriter(target, fieldnames=summary_rows[0].keys())
        writer.writeheader()
        writer.writerows(summary_rows)

    ensemble = add_province_membership(parse_tdump(ENSEMBLE["tdump"]), boundary_features)
    ensemble_rows = []
    for trajectory, group in ensemble.groupby("trajectory"):
        hit_rows = group.loc[group["source_province"].ne("")]
        counts = {province: int(group["source_province"].eq(province).sum()) for province in PROVINCES}
        ensemble_rows.append(
            {
                "event_date": ENSEMBLE["event_date"],
                "arrival": ENSEMBLE["arrival"],
                "noaa_job": ENSEMBLE["job"],
                "ensemble_member": int(trajectory),
                "arrival_height_m_agl": ENSEMBLE["arrival_height_m_agl"],
                "riau_hourly_endpoints": counts["Riau"],
                "jambi_hourly_endpoints": counts["Jambi"],
                "south_sumatra_hourly_endpoints": counts["Sumatera Selatan"],
                "intersects_selected_source": bool(len(hit_rows)),
                "oldest_age_inside_hours": hit_rows["age_hours"].min() if len(hit_rows) else "",
                "youngest_age_inside_hours": hit_rows["age_hours"].max() if len(hit_rows) else "",
            }
        )
    with ENSEMBLE_SUMMARY_FILE.open("w", newline="", encoding="utf-8") as target:
        writer = csv.DictWriter(target, fieldnames=ensemble_rows[0].keys())
        writer.writeheader()
        writer.writerows(ensemble_rows)
    print(SUMMARY_FILE)
    print(ENSEMBLE_SUMMARY_FILE)
    for event in EVENTS:
        print(event["output"])


if __name__ == "__main__":
    main()
