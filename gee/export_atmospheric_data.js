// George Town transboundary haze project: atmospheric data acquisition
// Study window: 1 August through 30 September 2019 (end date is exclusive).
// Run in the Google Earth Engine Code Editor after reviewing the geometries.

var START = ee.Date('2019-08-01');
var END = ee.Date('2019-10-01');

// Target and refined source geometries.
var georgeTown = ee.Geometry.Point([100.329, 5.414]);
var georgeTownBuffer = georgeTown.buffer(25000);
var indonesiaProvinces = ee.FeatureCollection('FAO/GAUL_SIMPLIFIED_500m/2015/level1')
  .filter(ee.Filter.eq('ADM0_NAME', 'Indonesia'));
var sourceProvinceNames = ee.List(['Riau', 'Jambi', 'Sumatera Selatan']);
var sumatraSourceRegion = indonesiaProvinces
  .filter(ee.Filter.inList('ADM1_NAME', sourceProvinceNames))
  .geometry();
var regionalExtent = ee.Geometry.Rectangle([98.0, -5.0, 106.0, 7.0]);

Map.centerObject(regionalExtent, 6);
Map.addLayer(georgeTown, {color: 'yellow'}, 'George Town centre');
Map.addLayer(georgeTownBuffer, {color: 'cyan'}, 'George Town 25 km buffer');
Map.addLayer(sumatraSourceRegion, {color: 'red'}, 'Riau + Jambi + South Sumatra source region');
print('Selected source provinces', indonesiaProvinces
  .filter(ee.Filter.inList('ADM1_NAME', sourceProvinceNames))
  .aggregate_array('ADM1_NAME'));

var numberOfDays = END.difference(START, 'day');
var offsets = ee.List.sequence(0, numberOfDays.subtract(1));

// -----------------------------------------------------------------------------
// 1. MODIS MAIAC aerosol optical depth at 0.55 micrometres
// -----------------------------------------------------------------------------

function maskAndScaleAod(image) {
  var qa = image.select('AOD_QA');

  // MCD19A2 V6.1 bit definitions:
  // bits 0-2 = cloud mask (1 means clear)
  // bits 3-4 = land/water/snow mask (0 means land)
  // bits 5-7 = adjacency mask (0 means normal/clear)
  // bits 8-11 = AOD quality (0 means best quality)
  // bit 12 = glint mask (0 means no glint)
  var clear = qa.bitwiseAnd(7).eq(1);
  var land = qa.rightShift(3).bitwiseAnd(3).eq(0);
  var clearAdjacency = qa.rightShift(5).bitwiseAnd(7).eq(0);
  var bestQuality = qa.rightShift(8).bitwiseAnd(15).eq(0);
  var noGlint = qa.rightShift(12).bitwiseAnd(1).eq(0);

  return image
    .select('Optical_Depth_055')
    .multiply(0.001)
    .rename('AOD_055')
    .updateMask(clear.and(land).and(clearAdjacency).and(bestQuality).and(noGlint))
    .copyProperties(image, ['system:time_start']);
}

var aodCollection = ee.ImageCollection('MODIS/061/MCD19A2_GRANULES')
  .filterDate(START, END)
  .filterBounds(georgeTownBuffer)
  .map(maskAndScaleAod);

var dailyAod = ee.FeatureCollection(offsets.map(function(offset) {
  var date = START.advance(ee.Number(offset), 'day');
  var nextDate = date.advance(1, 'day');
  var dailyImages = aodCollection.filterDate(date, nextDate);
  var dailyImage = dailyImages.mean();

  var median = dailyImage.reduceRegion({
    reducer: ee.Reducer.median(),
    geometry: georgeTownBuffer,
    scale: 1000,
    maxPixels: 1e7
  }).get('AOD_055');

  var mean = dailyImage.reduceRegion({
    reducer: ee.Reducer.mean(),
    geometry: georgeTownBuffer,
    scale: 1000,
    maxPixels: 1e7
  }).get('AOD_055');

  var validPixels = dailyImage.reduceRegion({
    reducer: ee.Reducer.count(),
    geometry: georgeTownBuffer,
    scale: 1000,
    maxPixels: 1e7
  }).get('AOD_055');

  return ee.Feature(null, {
    date: date.format('YYYY-MM-dd'),
    aod_055_median: median,
    aod_055_mean: mean,
    valid_pixel_count: validPixels,
    source_image_count: dailyImages.size()
  });
}));

print('Daily best-quality MAIAC AOD', dailyAod.limit(10));

Export.table.toDrive({
  collection: dailyAod,
  description: 'george_town_daily_maiac_aod_2019_aug_sep',
  folder: 'Penang_Haze_2019',
  fileNamePrefix: 'george_town_daily_maiac_aod_2019-08-01_2019-09-30',
  fileFormat: 'CSV'
});

// -----------------------------------------------------------------------------
// 2. Sentinel-5P Offline Absorbing Aerosol Index
// Earth Engine already excludes source pixels below the documented validity
// threshold during ingestion of this collection.
// -----------------------------------------------------------------------------

var aerosolIndexCollection = ee.ImageCollection('COPERNICUS/S5P/OFFL/L3_AER_AI')
  .filterDate(START, END)
  .filterBounds(regionalExtent)
  .select('absorbing_aerosol_index');

var dailyAerosolIndex = ee.FeatureCollection(offsets.map(function(offset) {
  var date = START.advance(ee.Number(offset), 'day');
  var nextDate = date.advance(1, 'day');
  var dailyImages = aerosolIndexCollection.filterDate(date, nextDate);
  var dailyImage = dailyImages.mean();

  var penangMean = dailyImage.reduceRegion({
    reducer: ee.Reducer.mean(),
    geometry: georgeTownBuffer,
    scale: 5000,
    maxPixels: 1e7
  }).get('absorbing_aerosol_index');

  var regionalMean = dailyImage.reduceRegion({
    reducer: ee.Reducer.mean(),
    geometry: regionalExtent,
    scale: 5000,
    maxPixels: 1e7
  }).get('absorbing_aerosol_index');

  return ee.Feature(null, {
    date: date.format('YYYY-MM-dd'),
    penang_aerosol_index_mean: penangMean,
    regional_aerosol_index_mean: regionalMean,
    source_image_count: dailyImages.size()
  });
}));

print('Daily Sentinel-5P Aerosol Index', dailyAerosolIndex.limit(10));

Export.table.toDrive({
  collection: dailyAerosolIndex,
  description: 'penang_daily_s5p_aerosol_index_2019_aug_sep',
  folder: 'Penang_Haze_2019',
  fileNamePrefix: 'penang_daily_s5p_aerosol_index_2019-08-01_2019-09-30',
  fileFormat: 'CSV'
});

var septemberAerosolIndex = aerosolIndexCollection
  .filterDate('2019-09-01', '2019-10-01')
  .mean();

Map.addLayer(
  septemberAerosolIndex.clip(regionalExtent),
  {min: -1, max: 3, palette: ['navy', 'blue', 'cyan', 'yellow', 'orange', 'red']},
  'September 2019 mean Aerosol Index'
);

// -----------------------------------------------------------------------------
// 3. ERA5 daily mean regional wind components
// -----------------------------------------------------------------------------

var windCollection = ee.ImageCollection('ECMWF/ERA5/HOURLY')
  .filterDate(START, END)
  .filterBounds(regionalExtent)
  .select([
    'u_component_of_wind_10m',
    'v_component_of_wind_10m',
    'u_component_of_wind_850hPa',
    'v_component_of_wind_850hPa'
  ]);

function regionMean(image, band, geometry) {
  return image.select(band).reduceRegion({
    reducer: ee.Reducer.mean(),
    geometry: geometry,
    scale: 30000,
    maxPixels: 1e7
  }).get(band);
}

var dailyWind = ee.FeatureCollection(offsets.map(function(offset) {
  var date = START.advance(ee.Number(offset), 'day');
  var nextDate = date.advance(1, 'day');
  var dailyImages = windCollection.filterDate(date, nextDate);
  var dailyImage = dailyImages.mean();

  return ee.Feature(null, {
    date: date.format('YYYY-MM-dd'),
    penang_u10_mps: regionMean(dailyImage, 'u_component_of_wind_10m', georgeTownBuffer),
    penang_v10_mps: regionMean(dailyImage, 'v_component_of_wind_10m', georgeTownBuffer),
    penang_u850_mps: regionMean(dailyImage, 'u_component_of_wind_850hPa', georgeTownBuffer),
    penang_v850_mps: regionMean(dailyImage, 'v_component_of_wind_850hPa', georgeTownBuffer),
    source_u10_mps: regionMean(dailyImage, 'u_component_of_wind_10m', sumatraSourceRegion),
    source_v10_mps: regionMean(dailyImage, 'v_component_of_wind_10m', sumatraSourceRegion),
    source_u850_mps: regionMean(dailyImage, 'u_component_of_wind_850hPa', sumatraSourceRegion),
    source_v850_mps: regionMean(dailyImage, 'v_component_of_wind_850hPa', sumatraSourceRegion),
    hourly_image_count: dailyImages.size()
  });
}));

print('Daily ERA5 wind components', dailyWind.limit(10));

Export.table.toDrive({
  collection: dailyWind,
  description: 'penang_riau_jambi_south_sumatra_daily_era5_wind_2019_aug_sep',
  folder: 'Penang_Haze_2019',
  fileNamePrefix: 'penang_riau_jambi_south_sumatra_daily_era5_wind_2019-08-01_2019-09-30',
  fileFormat: 'CSV'
});
