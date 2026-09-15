// Persistent 5-tab bottom nav — Home / Map / Capture / Data / More, Capture
// centered and filled (a small FAB inline in the bar, matching the existing
// PrimaryFab treatment: navy fill, white icon — Vol.4.1's spatial-context
// exception doesn't apply here, this isn't a map overlay). Replaces the old
// screen-enum push/pop shell in App.tsx (dashboard -> map -> back) with tabs
// a surveyor can switch between directly, per the redesign spec.
import { View, Text, TouchableOpacity, StyleSheet, Platform } from 'react-native';
import { COLOR, SPACE, ELEVATION, FAB_PRIMARY_COLOR, isWeb } from '../theme';
import { Icon, type IconName } from './Icon';

export type TabName = 'home' | 'map' | 'capture' | 'data' | 'more';

const TABS: { key: TabName; label: string; icon: IconName }[] = [
  { key: 'home', label: 'Home', icon: 'home' },
  { key: 'map', label: 'Map', icon: 'map' },
  { key: 'capture', label: 'Capture', icon: 'capture' },
  { key: 'data', label: 'Data', icon: 'data' },
  { key: 'more', label: 'More', icon: 'more' },
];

export default function BottomNav({ active, onChange }: {
  active: TabName; onChange: (t: TabName) => void;
}) {
  return (
    <View style={s.bar}>
      {TABS.map((t) => {
        const isActive = t.key === active;
        if (t.key === 'capture') {
          return (
            <TouchableOpacity
              key={t.key} onPress={() => onChange(t.key)} activeOpacity={0.85}
              style={[s.item, isWeb && ({ cursor: 'pointer' } as any)]}
            >
              <View style={s.captureFab}>
                <Icon name="capture" size={22} color="#fff" />
              </View>
              <Text style={[s.label, s.captureLabel]}>{t.label}</Text>
            </TouchableOpacity>
          );
        }
        return (
          <TouchableOpacity
            key={t.key} onPress={() => onChange(t.key)} activeOpacity={0.7}
            style={[s.item, isWeb && ({ cursor: 'pointer' } as any)]}
          >
            <Icon name={t.icon} size={22} color={isActive ? COLOR.primary900 : COLOR.text500} />
            <Text style={[s.label, isActive && s.labelActive]}>{t.label}</Text>
          </TouchableOpacity>
        );
      })}
    </View>
  );
}

const s = StyleSheet.create({
  bar: {
    flexDirection: 'row', alignItems: 'flex-start',
    backgroundColor: COLOR.surface0, borderTopWidth: 1, borderTopColor: COLOR.borderCard,
    paddingTop: SPACE.xs + 2, paddingBottom: Platform.OS === 'ios' ? SPACE.lg : SPACE.xs + 2,
    ...ELEVATION[2],
  },
  item: { flex: 1, alignItems: 'center', justifyContent: 'flex-start', gap: 3, paddingVertical: 2 },
  label: { fontSize: 11, color: COLOR.text500, fontWeight: '600' },
  labelActive: { color: COLOR.primary900 },
  captureFab: {
    width: 40, height: 40, borderRadius: 20, backgroundColor: FAB_PRIMARY_COLOR,
    alignItems: 'center', justifyContent: 'center', marginTop: -6,
  },
  captureLabel: { color: COLOR.primary900 },
});
