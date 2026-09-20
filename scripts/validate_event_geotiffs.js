/** Validate the geospatial metadata and band order of Earth Engine event GeoTIFFs. */

const fs = require('fs');
const path = require('path');

const ROOT = path.resolve(__dirname, '..');
const INPUT = path.join(ROOT, 'data', 'raw', 'earth_engine', 'event_maps');
const OUTPUT = path.join(ROOT, 'data', 'processed', 'event_geotiff_validation.json');
const REQUESTED = {west: 95, south: -7, east: 108, north: 9};

const TYPE_SIZE = {1: 1, 2: 1, 3: 2, 4: 4, 5: 8, 6: 1, 7: 1, 8: 2, 9: 4, 10: 8, 11: 4, 12: 8};
const TAG_NAME = {
  256: 'width', 257: 'height', 258: 'bitsPerSample', 259: 'compression',
  270: 'imageDescription', 277: 'samplesPerPixel', 284: 'planarConfiguration',
  33550: 'modelPixelScale', 33922: 'modelTiepoint', 34735: 'geoKeyDirectory',
  34736: 'geoDoubleParams', 34737: 'geoAsciiParams', 42112: 'gdalMetadata',
  42113: 'gdalNoData',
};

function readTiff(filename) {
  const buffer = fs.readFileSync(filename);
  const marker = buffer.toString('ascii', 0, 2);
  if (!['II', 'MM'].includes(marker)) throw new Error(`${filename}: invalid TIFF byte-order marker`);
  const little = marker === 'II';
  const u16 = offset => little ? buffer.readUInt16LE(offset) : buffer.readUInt16BE(offset);
  const i16 = offset => little ? buffer.readInt16LE(offset) : buffer.readInt16BE(offset);
  const u32 = offset => little ? buffer.readUInt32LE(offset) : buffer.readUInt32BE(offset);
  const i32 = offset => little ? buffer.readInt32LE(offset) : buffer.readInt32BE(offset);
  const f32 = offset => little ? buffer.readFloatLE(offset) : buffer.readFloatBE(offset);
  const f64 = offset => little ? buffer.readDoubleLE(offset) : buffer.readDoubleBE(offset);
  const u64 = offset => Number(little ? buffer.readBigUInt64LE(offset) : buffer.readBigUInt64BE(offset));
  const version = u16(2);
  if (![42, 43].includes(version)) throw new Error(`${filename}: unsupported TIFF version ${version}`);
  const bigTiff = version === 43;
  if (bigTiff && (u16(4) !== 8 || u16(6) !== 0)) throw new Error(`${filename}: unsupported BigTIFF offset format`);

  function decode(type, count, offset) {
    if (type === 2) return buffer.toString('utf8', offset, offset + count).replace(/\0+$/, '');
    const values = [];
    for (let index = 0; index < count; index += 1) {
      const at = offset + index * TYPE_SIZE[type];
      if (type === 1 || type === 7) values.push(buffer.readUInt8(at));
      else if (type === 3) values.push(u16(at));
      else if (type === 4) values.push(u32(at));
      else if (type === 5) values.push(u32(at) / u32(at + 4));
      else if (type === 6) values.push(buffer.readInt8(at));
      else if (type === 8) values.push(i16(at));
      else if (type === 9) values.push(i32(at));
      else if (type === 10) values.push(i32(at) / i32(at + 4));
      else if (type === 11) values.push(f32(at));
      else if (type === 12) values.push(f64(at));
      else throw new Error(`${filename}: unsupported TIFF field type ${type}`);
    }
    return values.length === 1 ? values[0] : values;
  }

  const ifd = bigTiff ? u64(8) : u32(4);
  const count = bigTiff ? u64(ifd) : u16(ifd);
  const tags = {};
  for (let index = 0; index < count; index += 1) {
    const entry = ifd + (bigTiff ? 8 : 2) + index * (bigTiff ? 20 : 12);
    const tag = u16(entry);
    const type = u16(entry + 2);
    const valueCount = bigTiff ? u64(entry + 4) : u32(entry + 4);
    const byteCount = (TYPE_SIZE[type] || 0) * valueCount;
    if (!TAG_NAME[tag] || !TYPE_SIZE[type]) continue;
    const inlineSize = bigTiff ? 8 : 4;
    const valueField = entry + (bigTiff ? 12 : 8);
    const valueOffset = byteCount <= inlineSize ? valueField : (bigTiff ? u64(valueField) : u32(valueField));
    tags[TAG_NAME[tag]] = decode(type, valueCount, valueOffset);
  }
  return {byteOrder: marker, tiffVariant: bigTiff ? 'BigTIFF' : 'TIFF', tags};
}

function geoKeys(directory, doubles = [], ascii = '') {
  if (!Array.isArray(directory) || directory.length < 4) return {};
  const result = {};
  const names = {1024: 'modelType', 1025: 'rasterType', 2048: 'geographicCrs', 2054: 'angularUnits'};
  for (let index = 0; index < directory[3]; index += 1) {
    const start = 4 + index * 4;
    const [key, location, count, offset] = directory.slice(start, start + 4);
    let value = offset;
    if (location === 34736) value = doubles.slice(offset, offset + count);
    if (location === 34737) value = ascii.slice(offset, offset + count).replace(/\|$/, '');
    result[names[key] || `key_${key}`] = value;
  }
  return result;
}

function bandDescriptions(metadata, samples) {
  if (typeof metadata !== 'string') return [];
  const result = Array(samples).fill(null);
  const pattern = /<Item\s+name="DESCRIPTION"\s+sample="(\d+)"[^>]*>([^<]+)<\/Item>/g;
  for (const match of metadata.matchAll(pattern)) result[Number(match[1])] = match[2];
  return result;
}

function inspect(filename) {
  const {byteOrder, tiffVariant, tags} = readTiff(filename);
  const scale = tags.modelPixelScale;
  const tiepoint = tags.modelTiepoint;
  if (!Array.isArray(scale) || !Array.isArray(tiepoint)) throw new Error(`${filename}: missing GeoTIFF transform tags`);
  const width = Number(tags.width), height = Number(tags.height);
  const west = tiepoint[3] - tiepoint[0] * scale[0];
  const north = tiepoint[4] + tiepoint[1] * scale[1];
  const bounds = {west, south: north - height * scale[1], east: west + width * scale[0], north};
  const keys = geoKeys(tags.geoKeyDirectory, tags.geoDoubleParams, tags.geoAsciiParams);
  const descriptions = bandDescriptions(tags.gdalMetadata, Number(tags.samplesPerPixel));
  const coversRequested = bounds.west <= REQUESTED.west && bounds.south <= REQUESTED.south &&
    bounds.east >= REQUESTED.east && bounds.north >= REQUESTED.north;
  return {
    file: path.basename(filename), byteOrder, tiffVariant, width, height,
    samplesPerPixel: Number(tags.samplesPerPixel), bitsPerSample: tags.bitsPerSample,
    planarConfiguration: tags.planarConfiguration, pixelSizeDegrees: scale.slice(0, 2),
    bounds, requestedBounds: REQUESTED, coversRequested,
    geographicCrs: keys.geographicCrs, rasterType: keys.rasterType,
    bandDescriptions: descriptions, noData: tags.gdalNoData ?? null,
    metadataPresent: Boolean(tags.gdalMetadata),
  };
}

function main() {
  const files = fs.readdirSync(INPUT).filter(name => name.toLowerCase().endsWith('.tif')).sort();
  const rasters = files.map(name => inspect(path.join(INPUT, name)));
  for (const raster of rasters) {
    const expected = raster.file.startsWith('era5_') ? ['u850_mps', 'v850_mps'] : ['absorbing_aerosol_index'];
    raster.expectedBands = expected;
    raster.bandOrderVerified = JSON.stringify(raster.bandDescriptions) === JSON.stringify(expected);
    raster.valid = raster.geographicCrs === 4326 && raster.coversRequested && raster.bandOrderVerified;
  }
  const report = {
    result: rasters.every(raster => raster.valid) ? 'pass' : 'review required',
    rasters,
  };
  fs.writeFileSync(OUTPUT, `${JSON.stringify(report, null, 2)}\n`);
  console.log(JSON.stringify(report, null, 2));
  console.log(`Saved ${OUTPUT}`);
}

module.exports = {inspectGeoTiff: inspect};
if (require.main === module) main();
