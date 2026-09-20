# Reproducing the Penang haze analysis

## Software

- Python 3.12 or later
- Python packages listed in `requirements.txt`
- Node.js 20 or later and the `sharp` package listed in `package.json`
- Google Earth Engine access for the atmospheric exports
- NOAA READY HYSPLIT access for archived trajectory runs

The analysis was last verified with Python packages NumPy 2.3.5, pandas 3.0.1, and Pillow 12.3.0; Node.js 24.19.0; and Sharp 0.35.4 on Windows.

## Directory roles

- `data/raw/`: downloaded source data; do not edit.
- `data/processed/`: reproducible filtered and joined tables.
- `gee/`: Google Earth Engine acquisition and raster-export scripts.
- `scripts/`: local processing, analysis, and plotting code.
- `figures/`: selected publication figures.
- `DATA_AVAILABILITY.md`: source URLs and redistribution limitations.

## Processing order

1. Acquire the annual VIIRS-SNPP Indonesia archive and place it at `data/raw/firms/viirs-snpp_2019_Indonesia.csv`.
2. Obtain an Indonesian province boundary file containing Riau, Jambi, and Sumatera Selatan; the original private project used the source documented in `DATA_AVAILABILITY.md`.
3. Run `scripts/prepare_firms_refined.py` to create the province-assigned fire-event and daily tables.
4. Run `gee/export_atmospheric_data.js` in the Earth Engine Code Editor and download the daily atmospheric CSV exports named by the script.
5. Run `scripts/join_analyze_daily.py`. This creates the joined daily table, the primary lag-correlation table, and the statistical sensitivity table.
6. Run `gee/export_event_plumes.js` in Earth Engine and download the four event GeoTIFFs to `data/raw/earth_engine/event_maps/`.
7. Recreate the NOAA READY HYSPLIT configurations described in the report. Preserve both the PDF plots and endpoint `tdump` files under `outputs/hysplit/`.
8. Run `scripts/analyze_hysplit_events.py` to generate the province-intersection table and trajectory maps.
9. Run `scripts/validate_event_geotiffs.js` to verify the CRS, coordinate transform, coverage, and band order of all four event rasters.
10. Run `scripts/plot_event_plume_wind.js` to generate the plume/wind maps and paired event-evidence panels. The renderer reads the actual GeoTIFF bounds and band descriptions rather than assuming them.

## Core commands

```powershell
python scripts/prepare_firms_refined.py
python scripts/join_analyze_daily.py
python scripts/analyze_hysplit_events.py
npm install
npm run validate:geotiffs
node scripts/plot_event_plume_wind.js
```

## Expected checks

- Joined daily table: 61 rows and 61 unique dates.
- Valid quality-screened MAIAC AOD: 27 days.
- Primary correlation table: 32 rows.
- Sensitivity-check table: 28 rows.
- HYSPLIT province-intersection table: 27 rows, representing 2 high-AOD events plus 1 low-AOD control × 3 arrival heights × 3 provinces.
- HYSPLIT 22 September ensemble table: 27 rows, one for each 1,500 m meteorological ensemble member; 16 members intersect at least one selected source province.
- No missing ERA5 daily wind components.
- Missing AOD remains blank and is never converted to zero.
- `data/processed/event_geotiff_validation.json` reports `pass`, EPSG:4326, full requested-area coverage, and the expected AAI and u/v band descriptions.

## External steps not fully automated

Earth Engine and NOAA READY HYSPLIT runs require authenticated or interactive web interfaces. Settings are reported in the manuscript. The historical hourly API file is not redistributed because it came from a third-party APIMS-derived archive with unclear redistribution terms. Its aggregate validation results remain reported transparently; formal DOE pollutant data should replace it if obtained.

## Portability note

The SVG figures request Arial but permit the operating system's font fallback, so small text-layout differences may occur on another computer. The event-raster renderer now reads the embedded GeoTIFF coordinate transform, EPSG code, and band descriptions explicitly. The validator supports the little-endian BigTIFF structure produced by these Earth Engine exports.
