// GPS capture — the heart of field survey. Every asset and every photo is
// stamped with a coordinate and its accuracy, so the office can judge how much
// to trust the position.
import * as Location from 'expo-location';

export type Fix = { lat: number; lon: number; accuracy: number };

export async function ensurePermission(): Promise<boolean> {
  const { status } = await Location.requestForegroundPermissionsAsync();
  return status === 'granted';
}

export async function getFix(): Promise<Fix> {
  const ok = await ensurePermission();
  if (!ok) throw new Error('Location permission denied');
  try {
    const pos = await Location.getCurrentPositionAsync({
      accuracy: Location.Accuracy.Highest,
    });
    return {
      lat: pos.coords.latitude,
      lon: pos.coords.longitude,
      accuracy: pos.coords.accuracy ?? 999,
    };
  } catch (e) {
    // Highest accuracy demands a real GPS fix, which desktop/laptop browsers
    // (no GPS chip, Wi-Fi-based positioning only) and even phones indoors
    // often can't deliver — surfaces as kCLErrorLocationUnknown on macOS.
    // One retry at lower accuracy resolves most of these rather than making
    // the surveyor back out and try again by hand.
    const pos = await Location.getCurrentPositionAsync({
      accuracy: Location.Accuracy.Balanced,
    });
    return {
      lat: pos.coords.latitude,
      lon: pos.coords.longitude,
      accuracy: pos.coords.accuracy ?? 999,
    };
  }
}

// Watch position while the surveyor walks a route. Emits a fix roughly every
// `distanceIntervalM` metres. Returns a stop() function. Foreground only in
// Expo Go — keep the screen on while recording (a dev build adds background).
export async function watchRoute(
  distanceIntervalM: number,
  onPoint: (fix: Fix) => void,
): Promise<() => void> {
  const ok = await ensurePermission();
  if (!ok) throw new Error('Location permission denied');
  const sub = await Location.watchPositionAsync(
    { accuracy: Location.Accuracy.BestForNavigation,
      distanceInterval: distanceIntervalM, timeInterval: 2000 },
    (pos) => onPoint({
      lat: pos.coords.latitude, lon: pos.coords.longitude,
      accuracy: pos.coords.accuracy ?? 999,
    }),
  );
  return () => sub.remove();
}
