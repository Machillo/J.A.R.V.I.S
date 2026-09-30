// Minimal PNG reader/writer (Node built-ins only) for the store-asset pipeline.
//
// Store rule this module exists for: App Store Connect rejects screenshots with an alpha
// channel and Google Play asks for 24-bit PNG (no alpha). Headless Chromium writes RGBA,
// so every rendered image is flattened onto an opaque background and re-encoded as RGB.
import zlib from "node:zlib";

const SIGNATURE = Buffer.from([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a]);
const CHANNELS = { 0: 1, 2: 3, 4: 2, 6: 4 }; // gray, RGB, gray+alpha, RGBA (8-bit only)

const CRC_TABLE = new Uint32Array(256).map((_, n) => {
  let c = n;
  for (let k = 0; k < 8; k += 1) c = c & 1 ? 0xedb88320 ^ (c >>> 1) : c >>> 1;
  return c >>> 0;
});

function crc32(buffer) {
  let c = 0xffffffff;
  for (const byte of buffer) c = CRC_TABLE[(c ^ byte) & 0xff] ^ (c >>> 8);
  return (c ^ 0xffffffff) >>> 0;
}

function chunks(buffer) {
  if (!buffer.subarray(0, 8).equals(SIGNATURE)) throw new Error("not a PNG file");
  const list = [];
  for (let offset = 8; offset < buffer.length;) {
    const length = buffer.readUInt32BE(offset);
    const type = buffer.toString("latin1", offset + 4, offset + 8);
    list.push({ type, data: buffer.subarray(offset + 8, offset + 8 + length) });
    offset += 12 + length;
    if (type === "IEND") break;
  }
  return list;
}

/** Header facts only: width, height, bit depth, color type, whether it can carry alpha. */
export function pngInfo(buffer) {
  const ihdr = chunks(buffer).find((chunk) => chunk.type === "IHDR");
  if (!ihdr) throw new Error("PNG without IHDR");
  const colorType = ihdr.data[9];
  const hasTransparencyChunk = chunks(buffer).some((chunk) => chunk.type === "tRNS");
  return {
    width: ihdr.data.readUInt32BE(0),
    height: ihdr.data.readUInt32BE(4),
    bitDepth: ihdr.data[8],
    colorType,
    interlaced: ihdr.data[12] === 1,
    // Apple: "no alpha channels or transparencies"; tRNS is transparency too.
    alpha: colorType === 4 || colorType === 6 || hasTransparencyChunk,
  };
}

function paeth(a, b, c) {
  const p = a + b - c;
  const pa = Math.abs(p - a);
  const pb = Math.abs(p - b);
  const pc = Math.abs(p - c);
  if (pa <= pb && pa <= pc) return a;
  return pb <= pc ? b : c;
}

/** Decode an 8-bit, non-interlaced PNG into raw pixels. */
export function decodePng(buffer) {
  const info = pngInfo(buffer);
  const channels = CHANNELS[info.colorType];
  if (info.bitDepth !== 8 || !channels || info.interlaced) {
    throw new Error(`unsupported PNG (bit depth ${info.bitDepth}, color type ${info.colorType}, interlaced ${info.interlaced})`);
  }
  const compressed = Buffer.concat(chunks(buffer).filter((chunk) => chunk.type === "IDAT").map((chunk) => chunk.data));
  const raw = zlib.inflateSync(compressed);
  const stride = info.width * channels;
  const pixels = Buffer.alloc(stride * info.height);
  for (let y = 0; y < info.height; y += 1) {
    const filter = raw[y * (stride + 1)];
    const line = raw.subarray(y * (stride + 1) + 1, (y + 1) * (stride + 1));
    const out = pixels.subarray(y * stride, (y + 1) * stride);
    const prev = y ? pixels.subarray((y - 1) * stride, y * stride) : null;
    for (let x = 0; x < stride; x += 1) {
      const left = x >= channels ? out[x - channels] : 0;
      const up = prev ? prev[x] : 0;
      const upLeft = prev && x >= channels ? prev[x - channels] : 0;
      const value = line[x];
      if (filter === 0) out[x] = value;
      else if (filter === 1) out[x] = value + left;
      else if (filter === 2) out[x] = value + up;
      else if (filter === 3) out[x] = value + ((left + up) >> 1);
      else if (filter === 4) out[x] = value + paeth(left, up, upLeft);
      else throw new Error(`bad PNG filter ${filter}`);
    }
  }
  return { width: info.width, height: info.height, channels, pixels };
}

function chunk(type, data) {
  const header = Buffer.alloc(8);
  header.writeUInt32BE(data.length, 0);
  header.write(type, 4, "latin1");
  const crc = Buffer.alloc(4);
  crc.writeUInt32BE(crc32(Buffer.concat([header.subarray(4), data])), 0);
  return Buffer.concat([header, data, crc]);
}

/** Encode 8-bit RGB pixels (3 channels) as an opaque PNG: color type 2, no alpha, no tRNS. */
export function encodeRgbPng({ width, height, pixels }) {
  const stride = width * 3;
  if (pixels.length !== stride * height) throw new Error("pixel buffer does not match width x height x 3");
  const raw = Buffer.alloc((stride + 1) * height);
  for (let y = 0; y < height; y += 1) {
    raw[y * (stride + 1)] = 0; // filter: none
    pixels.copy(raw, y * (stride + 1) + 1, y * stride, (y + 1) * stride);
  }
  const ihdr = Buffer.alloc(13);
  ihdr.writeUInt32BE(width, 0);
  ihdr.writeUInt32BE(height, 4);
  ihdr[8] = 8; // bit depth
  ihdr[9] = 2; // RGB
  return Buffer.concat([
    SIGNATURE,
    chunk("IHDR", ihdr),
    chunk("IDAT", zlib.deflateSync(raw, { level: 9 })),
    chunk("IEND", Buffer.alloc(0)),
  ]);
}

/** Composite any decoded image onto an opaque background color and return RGB pixels. */
export function flattenToRgb(image, background = [255, 255, 255]) {
  const { width, height, channels, pixels } = image;
  const out = Buffer.alloc(width * height * 3);
  for (let i = 0; i < width * height; i += 1) {
    const src = i * channels;
    const gray = channels <= 2;
    const rgb = gray ? [pixels[src], pixels[src], pixels[src]] : [pixels[src], pixels[src + 1], pixels[src + 2]];
    const alpha = channels === 2 ? pixels[src + 1] : channels === 4 ? pixels[src + 3] : 255;
    for (let c = 0; c < 3; c += 1) {
      out[i * 3 + c] = Math.round((rgb[c] * alpha + background[c] * (255 - alpha)) / 255);
    }
  }
  return { width, height, pixels: out };
}

export function hexToRgb(hex) {
  const m = /^#?([0-9a-f]{6})$/i.exec(hex);
  if (!m) throw new Error(`not a #RRGGBB color: ${hex}`);
  const n = parseInt(m[1], 16);
  return [(n >> 16) & 255, (n >> 8) & 255, n & 255];
}
