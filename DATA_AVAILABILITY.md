# Data availability and redistribution

The public package contains selected processed analytical summaries, code, and figures. It does not contain the complete raw source-data collection.

## Publicly obtainable sources

- NASA FIRMS VIIRS active-fire archive: https://firms.modaps.eosdis.nasa.gov/
- MODIS MAIAC, Sentinel-5P, and ERA5 products through Google Earth Engine: see the collection identifiers and export scripts in `gee/`.
- NOAA READY HYSPLIT: https://www.ready.noaa.gov/HYSPLIT_traj.php
- Official Malaysian monthly air-pollution data: https://data.gov.my/data-catalogue/air_pollution
- DOSM Environment Statistics, Pulau Pinang, 2021: https://www.dosm.gov.my/portal-main/publication-estatistik-log?chapter_id=3631&document_id=983

## Files deliberately excluded

The raw APIMS-derived 2018-2022 archive and the hourly/daily API derivatives are excluded because the archive's redistribution licence is unclear. The report provides aggregate results and a transparent provenance statement. Researchers seeking the original observations should use the Malaysian Department of Environment data-request portal or obtain the source archive independently.

Google Earth Engine exports and HYSPLIT outputs can be regenerated using the documented scripts, settings, and job descriptions. Some web services require authentication or interactive submission.

## Reproducibility scope

The selected processed tables permit verification of the reported statistical summaries and trajectory-intersection results. Full regeneration from source requires reacquiring the third-party datasets from their named providers under their current terms.
