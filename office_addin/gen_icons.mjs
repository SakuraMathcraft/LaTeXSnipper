import { mkdirSync, readFileSync } from "fs";
import { join, dirname } from "path";
import { fileURLToPath } from "url";
import sharp from "sharp";

const __dirname = dirname(fileURLToPath(import.meta.url));
const ASSETS = join(__dirname, "assets");
const OUTPUT = join(__dirname, "public", "assets");
const SIZES = [16, 20, 24, 32, 40, 48, 64, 80];
const LINE_WEIGHTS = new Map([
  [16, 1],
  [20, 1],
  [24, 1],
  [32, 1],
  [40, 2],
  [48, 2],
  [64, 2],
  [80, 2],
]);
const ICONS = [
  "icon-editor",
  "icon-insert",
  "icon-ocr",
  "icon-load",
  "icon-delete",
  "icon-numbered",
  "icon-renumber",
  "icon-help",
];

mkdirSync(OUTPUT, { recursive: true });
for (const name of ICONS) {
  const svgPath = join(ASSETS, `${name}.svg`);
  const svg = readFileSync(svgPath, "utf8");
  for (const sz of SIZES) {
    const stroke = (LINE_WEIGHTS.get(sz) * 64) / sz;
    const renderedSvg = svg
      .replaceAll('stroke-width="4"', `stroke-width="${stroke}"`)
      .replaceAll('stroke-width="6"', `stroke-width="${stroke * 1.5}"`);
    await sharp(Buffer.from(renderedSvg)).resize(sz, sz).png().toFile(join(OUTPUT, `${name}-${sz}.png`));
    console.log(`  ${name}-${sz}.png`);
  }
}
console.log("Done.");
