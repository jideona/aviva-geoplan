// Native counterpart to mediaStamp.web.ts — burning GPS coordinates into a
// photo needs pixel-level image manipulation, which canvas provides for
// free on web but has no built-in equivalent on native (would need
// expo-image-manipulator or similar, not currently a dependency). Current
// scope is the PWA specifically, so native capture keeps the plain,
// unstamped photo for now — this no-op keeps ManholeScreen/BuildingScreen's
// capture() call site identical on both platforms.
export async function stampCoordinates(
  uri: string,
  _fix: { lat: number; lon: number; accuracy?: number },
): Promise<string> {
  return uri;
}
