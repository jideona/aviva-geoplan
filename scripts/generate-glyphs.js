const fs = require('fs');
const path = require('path');
const fontnik = require('fontnik');

const SRC = '/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf';
const STACK = 'Liberation Sans Regular';  // must match the name inside the PBF
const OUT = process.argv[2];
const END = 1023;                             // Latin + Latin-1 + punctuation

const font = fs.readFileSync(SRC);
const dir = path.join(OUT, STACK);
fs.mkdirSync(dir, { recursive: true });

let done = 0, ranges = [];
for (let start = 0; start <= END; start += 256) ranges.push(start);

(async () => {
  for (const start of ranges) {
    await new Promise((resolve, reject) => {
      fontnik.range({ font, start, end: start + 255 }, (err, buf) => {
        if (err) return reject(err);
        fs.writeFileSync(path.join(dir, `${start}-${start + 255}.pbf`), buf);
        done++;
        resolve();
      });
    });
  }
  console.log(`wrote ${done} glyph ranges to ${dir}`);
})();
