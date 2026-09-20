"""Join the daily fire, aerosol and wind records and calculate transport tests.

The analysis is intentionally exploratory. Correlations are reported with their
usable sample sizes and missing MAIAC observations remain missing.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
FIRE_EVENTS = ROOT / "data/processed/viirs_snpp_riau_jambi_south_sumatra_2019-08-01_2019-09-30.csv"
FIRE_DAILY = ROOT / "data/processed/viirs_snpp_riau_jambi_south_sumatra_daily_2019-08-01_2019-09-30.csv"
AOD_DAILY = ROOT / "data/raw/earth_engine/george_town_daily_maiac_aod_2019-08-01_2019-09-30.csv"
AI_DAILY = ROOT / "data/raw/earth_engine/penang_daily_s5p_aerosol_index_2019-08-01_2019-09-30.csv"
WIND_DAILY = ROOT / "data/raw/earth_engine/penang_riau_jambi_south_sumatra_daily_era5_wind_2019-08-01_2019-09-30.csv"

JOINED_OUTPUT = ROOT / "data/processed/penang_sumatra_daily_joined_2019-08-01_2019-09-30.csv"
CORRELATION_OUTPUT = ROOT / "data/processed/penang_sumatra_lag_correlations_2019.csv"
SENSITIVITY_OUTPUT = ROOT / "data/processed/penang_sumatra_sensitivity_checks_2019.csv"

GEORGE_TOWN_LAT = 5.414
GEORGE_TOWN_LON = 100.329


def clean_earth_engine(path: Path, prefix: str) -> pd.DataFrame:
    frame = pd.read_csv(path)
    frame = frame.drop(columns=["system:index", ".geo"], errors="ignore")
    frame["date"] = pd.to_datetime(frame["date"], format="%Y-%m-%d")
    if "source_image_count" in frame:
        frame = frame.rename(columns={"source_image_count": f"{prefix}_source_image_count"})
    return frame


def add_fire_centroids() -> pd.DataFrame:
    events = pd.read_csv(FIRE_EVENTS)
    events["date"] = pd.to_datetime(events["acq_date"], format="%Y-%m-%d")
    eligible = events.loc[
        events["type"].eq(0) & events["confidence"].isin(["n", "h"])
    ].copy()

    def summarize(group: pd.DataFrame) -> pd.Series:
        frp = group["frp"].clip(lower=0)
        if frp.sum() > 0:
            frp_lat = np.average(group["latitude"], weights=frp)
            frp_lon = np.average(group["longitude"], weights=frp)
        else:
            frp_lat = np.nan
            frp_lon = np.nan
        return pd.Series(
            {
                "fire_centroid_lat": group["latitude"].mean(),
                "fire_centroid_lon": group["longitude"].mean(),
                "frp_weighted_centroid_lat": frp_lat,
                "frp_weighted_centroid_lon": frp_lon,
            }
        )

    return eligible.groupby("date", sort=True).apply(summarize, include_groups=False).reset_index()


def add_transport_components(frame: pd.DataFrame) -> pd.DataFrame:
    mean_lat_radians = np.deg2rad((frame["fire_centroid_lat"] + GEORGE_TOWN_LAT) / 2)
    east = (GEORGE_TOWN_LON - frame["fire_centroid_lon"]) * np.cos(mean_lat_radians)
    north = GEORGE_TOWN_LAT - frame["fire_centroid_lat"]
    angular_distance = np.sqrt(east**2 + north**2)

    frame["route_east_unit"] = east / angular_distance
    frame["route_north_unit"] = north / angular_distance
    frame["fire_centroid_to_penang_km"] = angular_distance * 111.32

    for location in ("source", "penang"):
        for level in ("10", "850"):
            u = frame[f"{location}_u{level}_mps"]
            v = frame[f"{location}_v{level}_mps"]
            frame[f"{location}_wind_speed{level}_mps"] = np.sqrt(u**2 + v**2)
            frame[f"{location}_toward_penang{level}_mps"] = (
                u * frame["route_east_unit"] + v * frame["route_north_unit"]
            )

    for level in ("10", "850"):
        frame[f"corridor_toward_penang{level}_mps"] = (
            frame[f"source_toward_penang{level}_mps"]
            + frame[f"penang_toward_penang{level}_mps"]
        ) / 2
        frame[f"both_locations_toward_penang{level}"] = (
            (frame[f"source_toward_penang{level}_mps"] > 0)
            & (frame[f"penang_toward_penang{level}_mps"] > 0)
        )

    return frame


def correlation_table(frame: pd.DataFrame) -> pd.DataFrame:
    outcomes = {
        "MAIAC AOD mean": "aod_055_mean",
        "Penang S5P Aerosol Index mean": "penang_aerosol_index_mean",
    }
    fire_metrics = {
        "Eligible fire detections": "analysis_eligible_count",
        "Sampled eligible FRP (MW)": "analysis_eligible_frp_mw",
    }
    rows: list[dict] = []

    for lag in range(4):
        for metric_column in fire_metrics.values():
            frame[f"{metric_column}_lag{lag}"] = frame[metric_column].shift(lag)
        frame[f"favorable_850_lag{lag}"] = frame["both_locations_toward_penang850"].shift(lag)

    for outcome_label, outcome_column in outcomes.items():
        for metric_label, metric_column in fire_metrics.items():
            for lag in range(4):
                predictor = f"{metric_column}_lag{lag}"
                for scope, favorable_only in (("All available days", False), ("850 hPa toward Penang", True)):
                    subset = frame[[outcome_column, predictor, f"favorable_850_lag{lag}"]].copy()
                    if favorable_only:
                        subset = subset.loc[subset[f"favorable_850_lag{lag}"].eq(True)]
                    subset = subset.dropna(subset=[outcome_column, predictor])
                    rows.append(
                        {
                            "outcome": outcome_label,
                            "fire_metric": metric_label,
                            "lag_days": lag,
                            "scope": scope,
                            "n_pairs": len(subset),
                            "pearson_r": subset[outcome_column].corr(subset[predictor], method="pearson"),
                            "spearman_rho": subset[outcome_column].rank().corr(subset[predictor].rank()),
                        }
                    )

    return pd.DataFrame(rows)


def sensitivity_table(frame: pd.DataFrame) -> pd.DataFrame:
    """Return checks for AOD statistic, seasonality, trend, and wind timing.

    The primary correlation table is retained unchanged.  These checks expose
    how the result changes when reasonable analytical choices are varied.
    """
    rows: list[dict] = []

    def add_correlation(
        analysis_group: str,
        outcome_label: str,
        outcome: pd.Series,
        predictor: pd.Series,
        lag: int,
        scope: str,
        mask: pd.Series | None = None,
        notes: str = "",
    ) -> None:
        usable = outcome.notna() & predictor.notna()
        if mask is not None:
            usable &= mask.fillna(False)
        x = predictor.loc[usable]
        y = outcome.loc[usable]
        rows.append(
            {
                "analysis_group": analysis_group,
                "outcome": outcome_label,
                "predictor": "Eligible fire detections",
                "lag_days": lag,
                "scope": scope,
                "n_pairs": int(usable.sum()),
                "pearson_r": y.corr(x, method="pearson"),
                "spearman_rho": y.rank().corr(x.rank()),
                "notes": notes,
            }
        )

    # Mean-versus-median AOD sensitivity.
    for outcome_label, outcome_column in (
        ("MAIAC AOD mean", "aod_055_mean"),
        ("MAIAC AOD median", "aod_055_median"),
    ):
        for lag in range(4):
            add_correlation(
                "AOD statistic sensitivity",
                outcome_label,
                frame[outcome_column],
                frame["analysis_eligible_count"].shift(lag),
                lag,
                "All available days",
            )

    # Month-specific results reveal whether the full-period association is
    # consistent across August and September or mainly an event-regime result.
    months = frame["date"].dt.month
    for month, label in ((8, "August 2019"), (9, "September 2019")):
        for lag in (0, 1):
            add_correlation(
                "Month sensitivity",
                "MAIAC AOD mean",
                frame["aod_055_mean"],
                frame["analysis_eligible_count"].shift(lag),
                lag,
                label,
                months.eq(month),
            )

    # The main analysis applies the favourable-wind flag on the fire day.
    # Compare that decision with receptor-day and complete transit-window masks.
    favorable = frame["both_locations_toward_penang850"].astype(bool)
    for lag in range(4):
        predictor = frame["analysis_eligible_count"].shift(lag)
        fire_day = favorable.shift(lag)
        receptor_day = favorable
        full_window = pd.Series(False, index=frame.index, dtype=bool)
        for index in range(lag, len(frame)):
            full_window.iloc[index] = bool(favorable.iloc[index - lag : index + 1].all())
        for scope, mask, note in (
            (
                "Favourable on fire day",
                fire_day,
                "This is the definition used in the primary lag-correlation table.",
            ),
            (
                "Favourable on receptor day",
                receptor_day,
                "Wind flag is evaluated on the AOD observation day.",
            ),
            (
                "Favourable throughout lag window",
                full_window,
                "Every day from the fire observation through the AOD day is favourable.",
            ),
        ):
            add_correlation(
                "Wind timing sensitivity",
                "MAIAC AOD mean",
                frame["aod_055_mean"],
                predictor,
                lag,
                scope,
                mask,
                note,
            )

    # Simple linear detrending is an exploratory check for the August-to-
    # September regime shift. It is not a replacement for a time-series model.
    day_index = pd.Series(np.arange(len(frame), dtype=float), index=frame.index)
    for lag in (0, 1):
        predictor = frame["analysis_eligible_count"].shift(lag)
        outcome = frame["aod_055_mean"]
        usable = predictor.notna() & outcome.notna()
        t = day_index.loc[usable].to_numpy()
        x = predictor.loc[usable].to_numpy(dtype=float)
        y = outcome.loc[usable].to_numpy(dtype=float)
        x_residual = x - np.polyval(np.polyfit(t, x, 1), t)
        y_residual = y - np.polyval(np.polyfit(t, y, 1), t)
        rows.append(
            {
                "analysis_group": "Linear detrending sensitivity",
                "outcome": "Detrended MAIAC AOD mean",
                "predictor": "Detrended eligible fire detections",
                "lag_days": lag,
                "scope": "All available days",
                "n_pairs": len(x),
                "pearson_r": np.corrcoef(x_residual, y_residual)[0, 1],
                "spearman_rho": pd.Series(y_residual).rank().corr(pd.Series(x_residual).rank()),
                "notes": "Both variables were residualised against a linear day-index trend.",
            }
        )

    # Serial-dependence diagnostics use the complete daily index; missing AOD
    # means that only adjacent calendar days with retrievals contribute.
    for label, series in (
        ("Eligible fire detections", frame["analysis_eligible_count"]),
        ("MAIAC AOD mean", frame["aod_055_mean"]),
    ):
        previous = series.shift(1)
        usable = series.notna() & previous.notna()
        rows.append(
            {
                "analysis_group": "Serial dependence diagnostic",
                "outcome": label,
                "predictor": f"Previous-day {label}",
                "lag_days": 1,
                "scope": "Adjacent calendar days",
                "n_pairs": int(usable.sum()),
                "pearson_r": series.loc[usable].corr(previous.loc[usable]),
                "spearman_rho": series.loc[usable].rank().corr(previous.loc[usable].rank()),
                "notes": "Diagnostic only; daily observations should not be assumed independent.",
            }
        )

    return pd.DataFrame(rows)


def main() -> None:
    fire = pd.read_csv(FIRE_DAILY)
    fire["date"] = pd.to_datetime(fire["date"], format="%Y-%m-%d")

    joined = fire.merge(add_fire_centroids(), on="date", how="left", validate="one_to_one")
    joined = joined.merge(clean_earth_engine(AOD_DAILY, "aod"), on="date", how="left", validate="one_to_one")
    joined = joined.merge(clean_earth_engine(AI_DAILY, "s5p_ai"), on="date", how="left", validate="one_to_one")
    joined = joined.merge(clean_earth_engine(WIND_DAILY, "era5"), on="date", how="left", validate="one_to_one")
    joined = add_transport_components(joined).sort_values("date").reset_index(drop=True)

    correlations = correlation_table(joined)
    sensitivity = sensitivity_table(joined)

    date_columns = [column for column in joined if column == "date"]
    joined[date_columns] = joined[date_columns].apply(lambda column: column.dt.strftime("%Y-%m-%d"))
    float_columns = joined.select_dtypes(include=["float"]).columns
    joined[float_columns] = joined[float_columns].round(6)
    correlation_floats = correlations.select_dtypes(include=["float"]).columns
    correlations[correlation_floats] = correlations[correlation_floats].round(4)
    sensitivity_floats = sensitivity.select_dtypes(include=["float"]).columns
    sensitivity[sensitivity_floats] = sensitivity[sensitivity_floats].round(4)

    joined.to_csv(JOINED_OUTPUT, index=False)
    correlations.to_csv(CORRELATION_OUTPUT, index=False)
    sensitivity.to_csv(SENSITIVITY_OUTPUT, index=False)

    valid_aod = int(joined["aod_055_mean"].notna().sum())
    favorable_850 = int(joined["both_locations_toward_penang850"].sum())
    print(f"Joined rows: {len(joined)}")
    print(f"Valid MAIAC AOD days: {valid_aod}")
    print(f"Days with source and Penang 850 hPa flow toward receptor: {favorable_850}")
    print(f"Joined output: {JOINED_OUTPUT}")
    print(f"Correlation output: {CORRELATION_OUTPUT}")
    print(f"Sensitivity output: {SENSITIVITY_OUTPUT}")


if __name__ == "__main__":
    main()
