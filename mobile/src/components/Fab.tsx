// Floating Action Buttons — Vol.4.1 §09.
// Primary: Navy fill (system exception — never Signal Orange in spatial/map
// contexts, see theme.ts FAB_PRIMARY_COLOR), white icon/label, elevation.3,
// 56×56 circular. Secondary: white fill, navy icon, elevation.2, 48×48 —
// used for map controls (GPS centre, zoom, layers).
import { Text, TouchableOpacity, StyleSheet, type StyleProp, type ViewStyle } from 'react-native';
import { COLOR, ELEVATION, RADIUS, FAB_PRIMARY_COLOR, isWeb } from '../theme';

export function PrimaryFab({ label, onPress, disabled, style }: {
  label: string; onPress: () => void; disabled?: boolean; style?: StyleProp<ViewStyle>;
}) {
  return (
    <TouchableOpacity
      onPress={onPress} disabled={disabled} activeOpacity={0.85}
      style={[s.primary, disabled && { opacity: 0.5 }, isWeb && ({ cursor: 'pointer' } as any), style]}
    >
      <Text style={s.primaryText} numberOfLines={1}>{label}</Text>
    </TouchableOpacity>
  );
}

export function SecondaryFab({ icon, onPress, active, style }: {
  icon: string; onPress: () => void; active?: boolean; style?: StyleProp<ViewStyle>;
}) {
  return (
    <TouchableOpacity
      onPress={onPress} activeOpacity={0.85}
      style={[s.secondary, active && s.secondaryActive, isWeb && ({ cursor: 'pointer' } as any), style]}
    >
      <Text style={[s.secondaryIcon, active && { color: '#fff' }]}>{icon}</Text>
    </TouchableOpacity>
  );
}

const s = StyleSheet.create({
  primary: {
    minHeight: 56, minWidth: 56, borderRadius: RADIUS.full,
    backgroundColor: FAB_PRIMARY_COLOR,
    alignItems: 'center', justifyContent: 'center',
    paddingHorizontal: 20,
    ...ELEVATION[3],
  },
  primaryText: { color: '#fff', fontWeight: '700', fontSize: 14 },
  secondary: {
    width: 48, height: 48, borderRadius: RADIUS.full,
    backgroundColor: COLOR.surface0,
    alignItems: 'center', justifyContent: 'center',
    ...ELEVATION[2],
  },
  secondaryActive: { backgroundColor: COLOR.primary900 },
  secondaryIcon: { color: COLOR.primary900, fontSize: 18, fontWeight: '700' },
});
