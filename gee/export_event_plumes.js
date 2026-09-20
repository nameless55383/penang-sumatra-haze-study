// Event-scale plume and wind exports for the Penang transboundary haze project.
// Primary cases: 11 and 22 September 2019, the two highest valid George Town
// MAIAC AOD days in the joined August-September record.

var region = ee.Geometry.Rectangle([95.0, -7.0, 108.0, 9.0], null, false);
var georgeTown = ee.Geometry.Point([100.329, 5.414]);

var s5p = ee.ImageCollection('COPERNICUS/S5P/OFFL/L3_AER_AI')
  .filterBounds(region)
  .select('absorbing_aerosol_index');

var era5 = ee.ImageCollection('ECMWF/ERA5/HOURLY')
  .filterBounds(region)
  .select([
    'u_component_of_wind_850hPa',
    'v_component_of_wind_850hPa'
  ]);

function exportEvent(label, startDate, endDate, windDate) {
  var plume = s5p
    .filterDate(startDate, endDate)
    .mean()
    .rename('absorbing_aerosol_index');

  var windStart = ee.Date(windDate);
  var wind = era5
    .filterDate(windStart, windStart.advance(1, 'day'))
    .mean()
    .rename(['u850_mps', 'v850_mps']);

  Map.addLayer(
    plume.clip(region),
    {min: -1, max: 3, palette: ['1a237e', '1976d2', '00acc1', 'ffee58', 'fb8c00', 'b71c1c']},
    label + ' Sentinel-5P AI composite'
  );

  Export.image.toDrive({
    image: plume.toFloat(),
    description: 's5p_ai_' + label,
    folder: 'Penang_Haze_2019',
    fileNamePrefix: 's5p_ai_' + label,
    region: region,
    scale: 5000,
    crs: 'EPSG:4326',
    maxPixels: 1e9,
    fileFormat: 'GeoTIFF'
  });

  Export.image.toDrive({
    image: wind.toFloat(),
    description: 'era5_850hpa_wind_' + label,
    folder: 'Penang_Haze_2019',
    fileNamePrefix: 'era5_850hpa_wind_' + label,
    region: region,
    scale: 30000,
    crs: 'EPSG:4326',
    maxPixels: 1e8,
    fileFormat: 'GeoTIFF'
  });
}

// Two-day plume composites reduce orbital gaps while retaining event timing.
// Wind is the daily mean on the George Town AOD observation date.
exportEvent('2019-09-11', '2019-09-10', '2019-09-12', '2019-09-11');
exportEvent('2019-09-22', '2019-09-21', '2019-09-23', '2019-09-22');

Map.centerObject(region, 5);
Map.addLayer(georgeTown, {color: 'ffffff'}, 'George Town');
print('Event exports prepared: two Sentinel-5P composites and two ERA5 850 hPa wind rasters.');
