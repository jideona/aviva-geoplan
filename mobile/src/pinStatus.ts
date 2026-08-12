// Shared classification for manhole/handhole captures — used by both
// MapScreen.web.tsx (map pins) and DashboardScreen.tsx (Recent Captures
// status pills) so the two views can't drift out of sync with each other's
// colour/shape meaning (Vol.4.1 §10).
export type PinStatusName = 'synced' | 'pending' | 'flagged';
export type PinShapeName = 'square' | 'triangle' | 'circle' | 'house';

// Pin conditions that mean "needs attention" outrank sync state in the
// status colour — a synced-but-damaged manhole should still read orange,
// not teal (Vol.4.1 §10: orange means flagged, regardless of sync).
const FLAGGED_CONDITIONS = new Set(['poor', 'damaged', 'inaccessible', 'buried']);

export function pinStatus(a: { synced?: boolean; sub?: string }): PinStatusName {
  if (a.sub && FLAGGED_CONDITIONS.has(a.sub)) return 'flagged';
  return a.synced ? 'synced' : 'pending';
}

// Shape convention — per explicit instruction: manholes are square,
// handholes are triangle, "a clear distinction between them." This
// intentionally overrides the Claude Design mockup's circle/square
// convention, which was tried in an earlier pass and didn't match what was
// actually wanted. Read from `label`, which both write paths (map quick-drop
// and the full ManholeScreen form) set to the mode/type string; anything
// that isn't manhole/handhole (joint_chamber, footway_box, other) falls back
// to a plain circle.
export function pinShape(a: { label?: string; kind?: string }): PinShapeName {
  if (a.kind === 'building_photo') return 'house';
  if (a.label === 'manhole') return 'square';
  if (a.label === 'handhole') return 'triangle';
  return 'circle';
}
