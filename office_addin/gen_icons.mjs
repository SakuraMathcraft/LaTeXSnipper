import { readFileSync } from "fs";
import { join, dirname } from "path";
import { fileURLToPath } from "url";
import sharp from "sharp";

const __dirname = dirname(fileURLToPath(import.meta.url));
const ASSETS = join(__dirname, "assets");
const SIZES = [16, 32, 80];
const ICONS = [
  "icon-editor",
  "icon-insert",
  "icon-ocr",
  "icon-load",
  "icon-update",
  "icon-numbered",
  "icon-renumber",
];

for (const name of ICONS) {
  const svgPath = join(ASSETS, `${name}.svg`);
  const svg = readFileSync(svgPath);
  for (const sz of SIZES) {
    await sharp(svg).resize(sz, sz).png().toFile(join(ASSETS, `${name}-${sz}.png`));
    console.log(`  ${name}-${sz}.png`);
  }
}
console.log("Done.");
