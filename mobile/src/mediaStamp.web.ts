// Watermarks a captured photo with the GPS fix it was taken under — burns
// the coordinates directly into the image (a translucent Navy strip along
// the bottom, white text) so the location travels with the photo itself,
// not just the surrounding form. Web-only: canvas is a browser API with no
// native equivalent here. Native capture keeps the plain photo for now —
// see the no-op counterpart in mediaStamp.ts (Metro picks this file
// automatically on web via the .web.ts convention, same as MapScreen etc).
import { COLOR } from './theme';

function hexToRgba(hex: string, alpha: number): string {
  const n = parseInt(hex.replace('#', ''), 16);
  const r = (n >> 16) & 255, g = (n >> 8) & 255, b = n & 255;
  return `rgba(${r}, ${g}, ${b}, ${alpha})`;
}

function loadImage(uri: string): Promise<HTMLImageElement> {
  return new Promise((resolve, reject) => {
    const img = new Image();
    img.onload = () => resolve(img);
    img.onerror = () => reject(new Error('Could not load captured photo for stamping.'));
    img.src = uri;
  });
}

export async function stampCoordinates(
  uri: string,
  fix: { lat: number; lon: number; accuracy?: number },
): Promise<string> {
  const img = await loadImage(uri);
  const width = img.naturalWidth || img.width;
  const height = img.naturalHeight || img.height;
  if (!width || !height) return uri;

  const canvas = document.createElement('canvas');
  canvas.width = width;
  canvas.height = height;
  const ctx = canvas.getContext('2d');
  if (!ctx) return uri;
  ctx.drawImage(img, 0, 0, width, height);

  const label = `${fix.lat.toFixed(6)}, ${fix.lon.toFixed(6)}`
    + (fix.accuracy != null ? `   ±${Math.round(fix.accuracy)}m` : '');
  const barHeight = Math.max(36, Math.round(height * 0.055));
  ctx.fillStyle = hexToRgba(COLOR.primary900, 0.72);
  ctx.fillRect(0, height - barHeight, width, barHeight);

  const fontSize = Math.max(14, Math.round(barHeight * 0.42));
  ctx.font = `600 ${fontSize}px sans-serif`;
  ctx.fillStyle = '#FFFFFF';
  ctx.textBaseline = 'middle';
  ctx.fillText(label, 14, height - barHeight / 2, width - 28);

  return canvas.toDataURL('image/jpeg', 0.85);
}
