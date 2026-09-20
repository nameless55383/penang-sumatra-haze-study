"""Plot the refined source region, the former box, and eligible VIIRS detections."""

import json
from pathlib import Path

import pandas as pd
from PIL import Image, ImageDraw, ImageFont


BOUNDARY = Path("data/raw/boundaries/indonesia_provinces_2025.geojson")
FIRES = Path("data/processed/viirs_snpp_riau_jambi_south_sumatra_2019-08-01_2019-09-30.csv")
OUTPUT = Path("outputs/maps/refined_sumatra_source_boundary.png")
COLORS = {
    "Riau": (59, 130, 246),
    "Jambi": (245, 158, 11),
    "Sumatera Selatan": (239, 68, 68),
}

WIDTH, HEIGHT = 1500, 1700
LEFT, TOP, RIGHT, BOTTOM = 135, 150, 70, 150
LON_MIN, LON_MAX = 98.0, 106.4
LAT_MIN, LAT_MAX = -5.3, 6.1


def xy(lon, lat):
    plot_width = WIDTH - LEFT - RIGHT
    plot_height = HEIGHT - TOP - BOTTOM
    x = LEFT + (lon - LON_MIN) / (LON_MAX - LON_MIN) * plot_width
    y = TOP + (LAT_MAX - lat) / (LAT_MAX - LAT_MIN) * plot_height
    return round(x), round(y)


def polygon_parts(geometry):
    if geometry["type"] == "Polygon":
        return [geometry["coordinates"]]
    return geometry["coordinates"]


def font(size, bold=False):
    filename = "arialbd.ttf" if bold else "arial.ttf"
    return ImageFont.truetype(f"C:/Windows/Fonts/{filename}", size)


def dashed_line(draw, start, end, fill, width=3, dash=14):
    x1, y1 = start
    x2, y2 = end
    length = ((x2 - x1) ** 2 + (y2 - y1) ** 2) ** 0.5
    steps = max(1, int(length / dash))
    for step in range(0, steps, 2):
        a = step / steps
        b = min((step + 1) / steps, 1)
        draw.line(
            (
                x1 + (x2 - x1) * a,
                y1 + (y2 - y1) * a,
                x1 + (x2 - x1) * b,
                y1 + (y2 - y1) * b,
            ),
            fill=fill,
            width=width,
        )


with BOUNDARY.open(encoding="utf-8") as boundary_file:
    boundaries = json.load(boundary_file)

fires = pd.read_csv(FIRES)
fires = fires.loc[fires["type"].eq(0) & fires["confidence"].isin(["n", "h"])]

image = Image.new("RGB", (WIDTH, HEIGHT), "white")
draw = ImageDraw.Draw(image)

for lon in range(98, 107):
    x, _ = xy(lon, LAT_MIN)
    draw.line((x, TOP, x, HEIGHT - BOTTOM), fill=(220, 225, 232), width=1)
    draw.text((x, HEIGHT - BOTTOM + 16), f"{lon}°E", font=font(22), fill=(55, 65, 81), anchor="ma")
for lat in range(-5, 7):
    _, y = xy(LON_MIN, lat)
    draw.line((LEFT, y, WIDTH - RIGHT, y), fill=(220, 225, 232), width=1)
    label = f"{abs(lat)}°{'N' if lat > 0 else 'S' if lat < 0 else ''}"
    draw.text((LEFT - 14, y), label, font=font(22), fill=(55, 65, 81), anchor="rm")

overlay = Image.new("RGBA", image.size, (0, 0, 0, 0))
overlay_draw = ImageDraw.Draw(overlay)
for feature in boundaries["features"]:
    name = feature["properties"].get("name")
    if name not in COLORS:
        continue
    color = COLORS[name]
    for rings in polygon_parts(feature["geometry"]):
        exterior = [xy(lon, lat) for lon, lat in rings[0]]
        overlay_draw.polygon(exterior, fill=(*color, 55), outline=(*color, 220), width=2)
        for hole in rings[1:]:
            overlay_draw.polygon([xy(lon, lat) for lon, lat in hole], fill=(255, 255, 255, 255))
image = Image.alpha_composite(image.convert("RGBA"), overlay)

point_layer = Image.new("RGBA", image.size, (0, 0, 0, 0))
point_draw = ImageDraw.Draw(point_layer)
for province, color in COLORS.items():
    rows = fires.loc[fires["source_province"].eq(province)].iloc[::8]
    for row in rows.itertuples():
        x, y = xy(row.longitude, row.latitude)
        point_draw.ellipse((x - 2, y - 2, x + 2, y + 2), fill=(*color, 120))
image = Image.alpha_composite(image, point_layer)
draw = ImageDraw.Draw(image)

box_tl = xy(99.0, 2.5)
box_tr = xy(104.5, 2.5)
box_br = xy(104.5, -4.5)
box_bl = xy(99.0, -4.5)
for start, end in ((box_tl, box_tr), (box_tr, box_br), (box_br, box_bl), (box_bl, box_tl)):
    dashed_line(draw, start, end, (75, 75, 75, 255), width=3)

gx, gy = xy(100.329, 5.414)
draw.regular_polygon((gx, gy, 13), n_sides=5, rotation=-18, fill=(20, 20, 20, 255))
draw.text((gx + 20, gy), "George Town", font=font(25, bold=True), fill=(20, 20, 20), anchor="lm")

draw.rectangle((LEFT, TOP, WIDTH - RIGHT, HEIGHT - BOTTOM), outline=(30, 41, 59), width=3)
draw.text((WIDTH // 2, 42), "Refined 2019 Sumatra fire-source region", font=font(36, bold=True), fill=(23, 32, 51), anchor="ma")
draw.text((WIDTH // 2, 91), "Eligible VIIRS detections, 1 Aug–30 Sep 2019", font=font(27), fill=(55, 65, 81), anchor="ma")

legend_x, legend_y = LEFT + 24, HEIGHT - BOTTOM - 190
draw.rounded_rectangle((legend_x, legend_y, legend_x + 490, legend_y + 165), radius=12, fill=(255, 255, 255, 235), outline=(120, 128, 140), width=2)
for index, (name, color) in enumerate(COLORS.items()):
    y = legend_y + 28 + index * 38
    draw.rectangle((legend_x + 18, y - 9, legend_x + 42, y + 15), fill=(*color, 80), outline=(*color, 255), width=2)
    draw.text((legend_x + 55, y + 3), name, font=font(22), fill=(35, 42, 54), anchor="lm")
dashed_line(draw, (legend_x + 250, legend_y + 125), (legend_x + 310, legend_y + 125), (75, 75, 75, 255), width=3, dash=10)
draw.text((legend_x + 320, legend_y + 128), "former box", font=font(20), fill=(55, 55, 55), anchor="lm")

draw.text((WIDTH // 2, HEIGHT - 42), "Longitude", font=font(24), fill=(45, 55, 70), anchor="ma")

OUTPUT.parent.mkdir(parents=True, exist_ok=True)
image.convert("RGB").save(OUTPUT, quality=95)
print(OUTPUT)
