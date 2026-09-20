# Satellite investigation of transboundary haze from Sumatran fires to Penang

**Author:** Avelyn Lim Xing Rui  
**Version:** 1.0.0  
**Study period:** 1 August-30 September 2019  
**Repository:** https://github.com/nameless55383/penang-sumatra-haze-study  
**DOI:** https://doi.org/10.5281/zenodo.22858814  

This independent A-level research project investigates whether aerosol loading over George Town, Penang, during the 2019 Southeast Asian haze was consistent with transport from fires in Riau, Jambi, and South Sumatra.

The analysis combines:

- NASA FIRMS VIIRS active-fire detections;
- MODIS MAIAC aerosol optical depth;
- Sentinel-5P Absorbing Aerosol Index;
- ERA5 10 m and 850 hPa winds;
- NOAA HYSPLIT back trajectories and a trajectory ensemble; and
- ground-level Penang air-quality context.

## Main finding

The evidence is consistent with an important Sumatran fire influence, particularly on 11 September 2019. The 22 September event was more meteorologically complex and demonstrates that a single daily wind arrow or trajectory cannot represent every transport pathway. These results are a weight-of-evidence interpretation and do not prove that all aerosol over George Town originated in Sumatra.

## Repository contents

- `report/REPORT.md` - complete research report source.
- `report/Satellite_Investigation_Sumatran_Fires_Penang.pdf` - publication-ready report.
- `scripts/` - local processing, analysis, validation, and plotting code.
- `gee/` - Google Earth Engine acquisition and raster-export scripts.
- `data/processed/` - selected reproducible summary tables that are cleared for this public package.
- `figures/` - principal study maps and evidence panels.
- `REPRODUCIBILITY.md` - processing sequence and expected checks.
- `DATA_AVAILABILITY.md` - source-data access and redistribution limitations.

## Important data note

This repository intentionally excludes raw source datasets and the APIMS-derived hourly and daily API files. The historical API archive used for event-scale validation was reconstructed by a third party from Malaysia DOE APIMS, but its redistribution licence is unclear. Numerical results are documented in the report, while the underlying archive must be obtained independently or requested from DOE.

## Citation

Please cite this release as:

> Lim, A. X. R. (2026). *Satellite Investigation of Transboundary Haze Transport from Sumatran Fires to George Town, Penang* (Version 1.0.0). Zenodo. https://doi.org/10.5281/zenodo.22858814

## Licences

- Original code in `scripts/` and `gee/`: MIT Licence.
- Original report text and figures: Creative Commons Attribution 4.0 International (CC BY 4.0).
- Third-party data remain subject to their respective source terms and are not relicensed by this repository.

## Disclaimer

This is an independent student research project. It has not undergone formal peer review, and its findings do not represent the views of NASA, NOAA, ECMWF, ESA, Google, the Malaysian Department of Environment, or any other data provider.
