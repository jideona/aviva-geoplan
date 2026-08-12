// Segmented Control — Vol.4.1 §09. Pill-shaped toggle replacing dropdowns
// for mode switching (e.g. Manhole vs. Handhole). Surface/100 background;
// active segment uses Surface/0 with elevation.1.
import { Text, TouchableOpacity, View, StyleSheet } from 'react-native';
import { COLOR, RADIUS, ELEVATION, SPACE, MIN_TOUCH, isWeb } from '../theme';

export default function SegmentedControl<T extends string>({
  options, value, onChange,
}: {
  options: { value: T; label: string }[];
  value: T;
  onChange: (v: T) => void;
}) {
  return (
    <View style={s.track}>
      {options.map((opt) => {
        const active = opt.value === value;
        return (
          <TouchableOpacity
            key={opt.value}
            onPress={() => onChange(opt.value)}
            style={[s.segment, active && s.segmentActive, isWeb && ({ cursor: 'pointer' } as any)]}
          >
            <Text style={[s.label, active && s.labelActive]} numberOfLines={1}>{opt.label}</Text>
          </TouchableOpacity>
        );
      })}
    </View>
  );
}

const s = StyleSheet.create({
  track: {
    flexDirection: 'row', backgroundColor: COLOR.surface100,
    borderRadius: RADIUS.full, padding: 4, gap: 4,
  },
  segment: {
    flex: 1, minHeight: MIN_TOUCH - 8, borderRadius: RADIUS.full,
    alignItems: 'center', justifyContent: 'center', paddingHorizontal: SPACE.sm,
  },
  segmentActive: { backgroundColor: COLOR.surface0, ...ELEVATION[1] },
  label: { fontSize: 13, fontWeight: '600', color: COLOR.text500 },
  labelActive: { color: COLOR.primary900 },
});
