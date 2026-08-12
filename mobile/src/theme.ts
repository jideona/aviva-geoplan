// Aviva Networx Design System v1.0 — shared tokens for the field survey app.
// Source: Vol.1 Brand Identity, Vol.2 Digital Foundations, Vol.4.1 Mobile
// Supplement. Every screen/component should import from here rather than
// hardcoding hex values or ad-hoc spacing — that's the whole point of a
// token set (Vol.2 §01).
import { Platform, type TextStyle, type ViewStyle } from 'react-native';

// ---- Colour tokens (Vol.1 §03 / Vol.2 §01, light mode) ----
export const COLOR = {
  primary900: '#0D1B4B', // Deep Navy — dominant surfaces, primary text on light
  primary700: '#1A6FA8', // Brand Blue — secondary buttons, active nav
  primary500: '#2589C8', // Networx Blue — links, primary interactive elements
  success500: '#00C9A7', // Teal — success states, synced/connected
  accent500: '#FF6B35',  // Signal Orange — primary CTA fill, flagged/attention status
  accent700: '#E8590C',  // Signal Orange Deep — orange text on light backgrounds
  surface0: '#FFFFFF',
  surface100: '#F4F6F9',
  text900: '#1A1A1A',
  text500: '#6B7280',
  borderDefault: '#D0D5DD',
  error: '#D92D20',      // Defined error red — never reuse orange for errors (Vol.2 §03)
} as const;

// Dark mode (Vol.2 §01) — not wired up in the app shell yet (no theme
// switcher exists), but reserved here so a future dark-mode pass has the
// right values on hand instead of inventing new ones.
export const COLOR_DARK = {
  surface900: '#0A1230',
  surface800: '#16204A',
  text0: '#F4F6F9',
  text400: '#8C96B8',
  accent500: '#FF6B35',
} as const;

// ---- System exception (Vol.1 §03 / Vol.4.1 §system-exception) ----
// FABs in spatial/map contexts use Navy, not Signal Orange. Orange is
// reserved exclusively for status (flagged/attention pins, badges) in
// spatial views — sharing it with the FAB would make "orange on the map"
// stop meaning one consistent thing. Documented here, not just in the
// component, so it isn't "fixed" back to accent500 by someone who hasn't
// read Vol.4.1.
export const FAB_PRIMARY_COLOR = COLOR.primary900;

// ---- Spacing — 8-point system (Vol.2 §01) ----
export const SPACE = {
  xs: 4,
  sm: 8,
  md: 16,
  lg: 24,
  xl: 32,
  '2xl': 48,
  '3xl': 64,
} as const;

// ---- Radius (Vol.2 §01, amended by Vol.4.1 §prerequisites) ----
export const RADIUS = {
  sm: 4,
  md: 8,
  lg: 16,
  full: 9999,
} as const;

// ---- Elevation → RN shadow styles (Vol.2 §01, amended by Vol.4.1) ----
// react-native-web renders boxShadow from these on web; native platforms
// use elevation (Android) / shadow* (iOS) — RN accepts both sets of props
// on any platform harmlessly, so one object works everywhere.
function shadow(y: number, blur: number, alpha: number, androidElevation: number): ViewStyle {
  return {
    shadowColor: '#0D1B4B',
    shadowOffset: { width: 0, height: y },
    shadowOpacity: alpha,
    shadowRadius: blur,
    elevation: androidElevation,
  };
}
export const ELEVATION = {
  // Resting card, map pin
  1: shadow(1, 2, 0.08, 1),
  // Hover/raised card, dropdown, secondary FAB
  2: shadow(4, 12, 0.12, 3),
  // Modal, dialog, and docked highest-emphasis floating elements (primary FAB)
  3: shadow(12, 32, 0.18, 6),
  // Highest-priority surface — field-mode bottom sheets, above elevation.3 FABs
  4: shadow(20, 48, 0.24, 10),
} as const;

// ---- Typography (Vol.1 §04 / Vol.2 §02) ----
// DM Sans for headings/body, Space Mono for technical/data labels. Font
// files are loaded via @expo-google-fonts in App.tsx; these family names
// match what useFonts() registers there.
export const FONT = {
  sans: 'DMSans_400Regular',
  sansBold: 'DMSans_700Bold',
  mono: 'SpaceMono_400Regular',
} as const;

export const TYPE: Record<string, TextStyle> = {
  display: { fontFamily: FONT.sansBold, fontSize: 40, lineHeight: 48 },
  h1: { fontFamily: FONT.sansBold, fontSize: 28, lineHeight: 36 },
  h2: { fontFamily: FONT.sansBold, fontSize: 22, lineHeight: 30 },
  h3: { fontFamily: FONT.sansBold, fontSize: 18, lineHeight: 26 },
  body: { fontFamily: FONT.sans, fontSize: 15, lineHeight: 24 },
  bodyBold: { fontFamily: FONT.sansBold, fontSize: 15, lineHeight: 24 },
  small: { fontFamily: FONT.sans, fontSize: 13, lineHeight: 20 },
  mono: { fontFamily: FONT.mono, fontSize: 13, lineHeight: 20 },
};

// ---- Map pin / status colours (Vol.4.1 §10) ----
// Fixed meanings, never repurposed (Vol.2 §04): teal = synced/healthy,
// mid grey = pending/unsynced, orange = flagged/needs attention.
export const STATUS = {
  synced: COLOR.success500,
  pending: COLOR.text500,
  flagged: COLOR.accent500,
  currentLocation: COLOR.primary500,
};

// ---- Touch targets (Vol.2 §04 accessibility minimum) ----
export const MIN_TOUCH = 44;

// ---- Pressed-state helper (Vol.4.1 §12.1) ----
// Same transform/opacity/timing as the PWA app-shell's global :active rule,
// for native Pressable usage where CSS doesn't apply.
export const PRESSED_STYLE: ViewStyle = { transform: [{ scale: 0.98 }], opacity: 0.85 };

export const isWeb = Platform.OS === 'web';
