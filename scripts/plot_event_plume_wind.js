/** Render Earth Engine Sentinel-5P aerosol-index and ERA5 850 hPa wind maps. */

const fs = require('fs');
const path = require('path');
const sharp = require('sharp');
const {inspectGeoTiff} = require('./validate_event_geotiffs');

const ROOT = path.resolve(__dirname, '..');
const RAW = path.join(ROOT, 'data', 'raw', 'earth_engine', 'event_maps');
const OUT = path.join(ROOT, 'outputs', 'maps');
const BOUNDARIES = path.join(ROOT, 'data', 'raw', 'boundaries', 'indonesia_provinces_2025.geojson');
const FIRES = path.join(ROOT, 'data', 'processed', 'viirs_snpp_riau_jambi_south_sumatra_2019-08-01_2019-09-30.csv');
const JOINED = path.join(ROOT, 'data', 'processed', 'penang_sumatra_daily_joined_2019-08-01_2019-09-30.csv');

const EVENTS = ['2019-09-11', '2019-09-22'];
const SOURCE_PROVINCES = new Set(['Riau', 'Jambi', 'Sumatera Selatan']);
const W = 1700, H = 1280;
const LEFT = 135, TOP = 160, RIGHT = 95, BOTTOM = 180;
const PLOT_W = W - LEFT - RIGHT, PLOT_H = H - TOP - BOTTOM;
const LON_MIN = 95, LON_MAX = 108, LAT_MIN = -7, LAT_MAX = 9;

function esc(value) {
  return String(value).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&apos;'}[c]));
}

function x(lon) { return LEFT + (lon - LON_MIN) / (LON_MAX - LON_MIN) * PLOT_W; }
function y(lat) { return TOP + (LAT_MAX - lat) / (LAT_MAX - LAT_MIN) * PLOT_H; }

function parseCsv(filename) {
  const lines = fs.readFileSync(filename, 'utf8').trim().split(/\r?\n/);
  const headers = lines[0].split(',');
  return lines.slice(1).map(line => {
    const values = line.split(',');
    return Object.fromEntries(headers.map((header, index) => [header, values[index]]));
  });
}

function colour(value) {
  if (!Number.isFinite(value)) return [226, 232, 240];
  const stops = [
    [-2.0, [30, 58, 138]],
    [-1.0, [77, 145, 196]],
    [ 0.0, [224, 237, 240]],
    [ 1.0, [254, 224, 115]],
    [ 2.0, [244, 109, 67]],
    [ 3.5, [165, 0, 38]],
  ];
  if (value <= stops[0][0]) return stops[0][1];
  if (value >= stops.at(-1)[0]) return stops.at(-1)[1];
  for (let i = 0; i < stops.length - 1; i++) {
    if (value <= stops[i + 1][0]) {
      const t = (value - stops[i][0]) / (stops[i + 1][0] - stops[i][0]);
      return stops[i][1].map((v, j) => Math.round(v + t * (stops[i + 1][1][j] - v)));
    }
  }
}

async function readFloatTiff(filename) {
  return sharp(filename).raw({depth: 'float'}).toBuffer({resolveWithObject: true});
}

async function aerosolPng(filename, geo) {
  const {data, info} = await readFloatTiff(filename);
  const values = new Float32Array(data.buffer, data.byteOffset, data.byteLength / 4);
  const rgb = Buffer.alloc(info.width * info.height * 3);
  const sourceChannels = info.channels;
  let positive = 0, valid = 0, maximum = -Infinity;
  for (let i = 0; i < info.width * info.height; i++) {
    const row = Math.floor(i / info.width), col = i % info.width;
    const lon = geo.bounds.west + (col + 0.5) / info.width * (geo.bounds.east - geo.bounds.west);
    const lat = geo.bounds.north - (row + 0.5) / info.height * (geo.bounds.north - geo.bounds.south);
    const value = values[i * sourceChannels];
    const c = colour(value);
    rgb[i * 3] = c[0]; rgb[i * 3 + 1] = c[1]; rgb[i * 3 + 2] = c[2];
    if (lon >= LON_MIN && lon <= LON_MAX && lat >= LAT_MIN && lat <= LAT_MAX && Number.isFinite(value)) {
      valid++; if (value > 1) positive++; maximum = Math.max(maximum, value);
    }
  }
  const png = await sharp(rgb, {raw: {width: info.width, height: info.height, channels: 3}}).png().toBuffer();
  return {png, positiveFraction: positive / valid, maximum};
}

function geometryPaths(geometry) {
  const polygons = geometry.type === 'Polygon' ? [geometry.coordinates] : geometry.coordinates;
  return polygons.map(rings => rings.map(ring => ring.map(([lon, lat], i) => `${i ? 'L' : 'M'}${x(lon).toFixed(1)},${y(lat).toFixed(1)}`).join(' ') + ' Z').join(' '));
}

function arrowSvg(px, py, u, v) {
  const speed = Math.hypot(u, v);
  if (!Number.isFinite(speed) || speed < 0.05) return '';
  const length = Math.min(54, 17 + speed * 4.2);
  const dx = u / speed * length, dy = -v / speed * length;
  const ex = px + dx, ey = py + dy;
  const angle = Math.atan2(dy, dx), head = 8;
  const a1x = ex - head * Math.cos(angle - 0.55), a1y = ey - head * Math.sin(angle - 0.55);
  const a2x = ex - head * Math.cos(angle + 0.55), a2y = ey - head * Math.sin(angle + 0.55);
  return `<path d="M${px.toFixed(1)},${py.toFixed(1)} L${ex.toFixed(1)},${ey.toFixed(1)} M${ex.toFixed(1)},${ey.toFixed(1)} L${a1x.toFixed(1)},${a1y.toFixed(1)} M${ex.toFixed(1)},${ey.toFixed(1)} L${a2x.toFixed(1)},${a2y.toFixed(1)}" stroke="#101827" stroke-width="3.2" stroke-linecap="round" fill="none" opacity="0.92"/>`;
}

async function render(event, boundaries, fires, daily) {
  const aiFile = path.join(RAW, `s5p_ai_${event}.tif`);
  const windFile = path.join(RAW, `era5_850hpa_wind_${event}.tif`);
  const aiGeo = inspectGeoTiff(aiFile);
  const windGeo = inspectGeoTiff(windFile);
  if (aiGeo.geographicCrs !== 4326 || windGeo.geographicCrs !== 4326) throw new Error('Event rasters must use EPSG:4326');
  if (JSON.stringify(aiGeo.bandDescriptions) !== JSON.stringify(['absorbing_aerosol_index'])) throw new Error(`Unexpected AAI band order in ${aiFile}`);
  if (JSON.stringify(windGeo.bandDescriptions) !== JSON.stringify(['u850_mps', 'v850_mps'])) throw new Error(`Unexpected wind band order in ${windFile}`);
  const ai = await aerosolPng(aiFile, aiGeo);
  const {data: windData, info: windInfo} = await readFloatTiff(windFile);
  const wind = new Float32Array(windData.buffer, windData.byteOffset, windData.byteLength / 4);

  let grids = '';
  for (let lon = 96; lon <= 108; lon += 2) grids += `<line x1="${x(lon)}" y1="${TOP}" x2="${x(lon)}" y2="${TOP + PLOT_H}" class="grid"/><text x="${x(lon)}" y="${TOP + PLOT_H + 34}" class="tick" text-anchor="middle">${lon}°E</text>`;
  for (let lat = -6; lat <= 8; lat += 2) grids += `<line x1="${LEFT}" y1="${y(lat)}" x2="${LEFT + PLOT_W}" y2="${y(lat)}" class="grid"/><text x="${LEFT - 18}" y="${y(lat) + 7}" class="tick" text-anchor="end">${Math.abs(lat)}°${lat > 0 ? 'N' : lat < 0 ? 'S' : ''}</text>`;

  let provinceSvg = '';
  for (const feature of boundaries.features) {
    const name = feature.properties?.name || '';
    const source = SOURCE_PROVINCES.has(name);
    for (const d of geometryPaths(feature.geometry)) {
      provinceSvg += `<path d="${d}" fill="${source ? '#f9731624' : 'none'}" stroke="${source ? '#7c2d12' : '#334155'}" stroke-width="${source ? 2.4 : 1.1}" vector-effect="non-scaling-stroke"/>`;
    }
  }

  const eventTime = Date.parse(event + 'T00:00:00Z');
  const fireStart = eventTime - 2 * 86400000;
  const eventFires = fires.filter(row => {
    const t = Date.parse(row.acq_date + 'T00:00:00Z');
    return t >= fireStart && t <= eventTime && row.type === '0' && (row.confidence === 'n' || row.confidence === 'h');
  });
  const fireStep = Math.max(1, Math.ceil(eventFires.length / 1800));
  let fireSvg = '';
  for (let i = 0; i < eventFires.length; i += fireStep) {
    const row = eventFires[i], lon = Number(row.longitude), lat = Number(row.latitude);
    if (lon >= LON_MIN && lon <= LON_MAX && lat >= LAT_MIN && lat <= LAT_MAX) fireSvg += `<circle cx="${x(lon).toFixed(1)}" cy="${y(lat).toFixed(1)}" r="2.7" fill="#b91c1c" opacity="0.58"/>`;
  }

  let windSvg = '';
  const channels = windInfo.channels;
  for (let row = 2; row < windInfo.height; row += 5) {
    for (let col = 2; col < windInfo.width; col += 5) {
      const index = (row * windInfo.width + col) * channels;
      const u = wind[index], v = wind[index + channels - 1];
      const lon = windGeo.bounds.west + (col + 0.5) / windInfo.width * (windGeo.bounds.east - windGeo.bounds.west);
      const lat = windGeo.bounds.north - (row + 0.5) / windInfo.height * (windGeo.bounds.north - windGeo.bounds.south);
      if (lon >= LON_MIN && lon <= LON_MAX && lat >= LAT_MIN && lat <= LAT_MAX) windSvg += arrowSvg(x(lon), y(lat), u, v);
    }
  }

  const row = daily[event];
  const evidence = `George Town MAIAC AOD ${Number(row.aod_055_mean).toFixed(3)}  •  eligible fires ${Number(row.analysis_eligible_count).toLocaleString('en-US')}  •  source→Penang wind ${Number(row.source_toward_penang850_mps).toFixed(2)} m/s`;
  const note = event === '2019-09-11'
    ? 'Interpretation: favourable regional flow; test source attribution against all three HYSPLIT arrival heights.'
    : 'Interpretation: favourable daily-mean flow, but HYSPLIT reveals strong height-dependent transport.';
  const gx = x(100.329), gy = y(5.414);
  const image64 = ai.png.toString('base64');
  const aiX = x(aiGeo.bounds.west), aiY = y(aiGeo.bounds.north);
  const aiWidth = (aiGeo.bounds.east - aiGeo.bounds.west) / (LON_MAX - LON_MIN) * PLOT_W;
  const aiHeight = (aiGeo.bounds.north - aiGeo.bounds.south) / (LAT_MAX - LAT_MIN) * PLOT_H;

  const svg = `
  <svg width="${W}" height="${H}" xmlns="http://www.w3.org/2000/svg">
    <style>
      text{font-family:Arial,sans-serif;fill:#172033}.title{font-size:40px;font-weight:700}.sub{font-size:24px;fill:#475569}.tick{font-size:20px;fill:#475569}.grid{stroke:#fff;stroke-width:1;opacity:.34}.legend{font-size:21px}.note{font-size:22px;font-weight:600;fill:#334155}
    </style>
    <rect width="100%" height="100%" fill="#f8fafc"/>
    <text x="${W/2}" y="52" text-anchor="middle" class="title">Satellite plume and 850 hPa wind: ${event}</text>
    <text x="${W/2}" y="94" text-anchor="middle" class="sub">Sentinel-5P absorbing aerosol index (two-day mean composite) • ERA5 daily-mean wind</text>
    <text x="${W/2}" y="130" text-anchor="middle" class="sub">${esc(evidence)}</text>
    <defs><clipPath id="plotClip"><rect x="${LEFT}" y="${TOP}" width="${PLOT_W}" height="${PLOT_H}"/></clipPath></defs>
    <image href="data:image/png;base64,${image64}" x="${aiX}" y="${aiY}" width="${aiWidth}" height="${aiHeight}" preserveAspectRatio="none" clip-path="url(#plotClip)"/>
    ${grids}${provinceSvg}${fireSvg}${windSvg}
    <rect x="${LEFT}" y="${TOP}" width="${PLOT_W}" height="${PLOT_H}" fill="none" stroke="#172033" stroke-width="3"/>
    <path d="M${gx},${gy-13} L${gx+4},${gy-4} L${gx+14},${gy-4} L${gx+6},${gy+3} L${gx+9},${gy+14} L${gx},${gy+8} L${gx-9},${gy+14} L${gx-6},${gy+3} L${gx-14},${gy-4} L${gx-4},${gy-4} Z" fill="#020617" stroke="#fff" stroke-width="2"/>
    <text x="${gx+20}" y="${gy-10}" class="legend" font-weight="700">George Town</text>
    <g transform="translate(${LEFT+22},${TOP+PLOT_H-154})">
      <rect width="590" height="132" rx="12" fill="#ffffff" opacity=".92" stroke="#64748b"/>
      <circle cx="28" cy="32" r="5" fill="#b91c1c" opacity=".7"/><text x="48" y="40" class="legend">VIIRS fires, event day and prior 2 days</text>
      <path d="M25,71 L91,71 M91,71 L80,63 M91,71 L80,79" stroke="#101827" stroke-width="4" fill="none"/><text x="110" y="78" class="legend">ERA5 850 hPa wind (arrow points downwind)</text>
      <rect x="21" y="98" width="20" height="16" fill="#f9731640" stroke="#7c2d12"/><text x="51" y="113" class="legend">Riau + Jambi + Sumatera Selatan</text>
    </g>
    <g transform="translate(${W-430},${TOP+PLOT_H-147})">
      <rect width="390" height="124" rx="12" fill="#ffffff" opacity=".92" stroke="#64748b"/>
      <text x="18" y="28" class="legend" font-weight="700">Absorbing aerosol index</text>
      <defs><linearGradient id="cb"><stop offset="0" stop-color="#1e3a8a"/><stop offset="33%" stop-color="#e0edf0"/><stop offset="58%" stop-color="#fee073"/><stop offset="80%" stop-color="#f46d43"/><stop offset="100%" stop-color="#a50026"/></linearGradient></defs>
      <rect x="18" y="43" width="350" height="27" fill="url(#cb)" stroke="#475569"/>
      <text x="18" y="94" class="tick">−2</text><text x="130" y="94" class="tick">0</text><text x="245" y="94" class="tick">2</text><text x="358" y="94" class="tick" text-anchor="end">3.5+</text>
    </g>
    <text x="${W/2}" y="${H-72}" text-anchor="middle" class="note">${esc(note)}</text>
    <text x="${W/2}" y="${H-38}" text-anchor="middle" class="tick">AI pixels &gt; 1: ${(100*ai.positiveFraction).toFixed(1)}% • maximum ${ai.maximum.toFixed(2)} • maps are evidence of aerosol and transport compatibility, not proof of source by themselves</text>
  </svg>`;

  fs.mkdirSync(OUT, {recursive: true});
  const output = path.join(OUT, `plume_wind_${event}.png`);
  await sharp(Buffer.from(svg)).png().toFile(output);
  console.log(output);
}

async function main() {
  const boundaries = JSON.parse(fs.readFileSync(BOUNDARIES, 'utf8'));
  const fires = parseCsv(FIRES);
  const daily = Object.fromEntries(parseCsv(JOINED).map(row => [row.date, row]));
  for (const event of EVENTS) {
    await render(event, boundaries, fires, daily);
    const plume = path.join(OUT, `plume_wind_${event}.png`);
    const trajectories = path.join(OUT, `hysplit_event_${event}.png`);
    const right = await sharp(trajectories).resize({height: H}).png().toBuffer();
    const rightMeta = await sharp(right).metadata();
    await sharp({create: {width: W + rightMeta.width, height: H, channels: 3, background: '#f8fafc'}})
      .composite([{input: plume, left: 0, top: 0}, {input: right, left: W, top: 0}])
      .png()
      .toFile(path.join(OUT, `event_evidence_${event}.png`));
  }
}

main().catch(error => { console.error(error); process.exitCode = 1; });
