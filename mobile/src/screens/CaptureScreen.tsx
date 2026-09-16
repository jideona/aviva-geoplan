// Capture tab — a full-screen picker (design bundle screen 3), not a sheet
// opened from Home's quick actions. Building/Manhole/Photo hand off to the
// existing capture sheets (unchanged flows); Track Route hands off to the
// Map tab's existing route-recording mode (no new capture surface needed —
// it already exists there, just wasn't reachable from a dedicated nav
// destination). Road/Street has no backend capture endpoint yet (Street is
// still office-only, see PR plan) — shown, disabled, "coming soon" rather
// than hidden, so the nav's shape matches the design now and lights up once
// PR 5 adds the mobile-facing street endpoints.
import { View, Text, TouchableOpacity, StyleSheet } from 'react-native';
import { COLOR, SPACE, RADIUS, TYPE, MIN_TOUCH, isWeb } from '../theme';
import { Icon, type IconName } from '../components/Icon';

type CaptureKind = 'manhole' | 'building' | 'building_photo' | 'street' | 'route';

export default function CaptureScreen({ onPick, onOpenMap }: {
  onPick: (kind: CaptureKind) => void;
  onOpenMap: () => void;
}) {
  return (
    <View style={{ flex: 1, backgroundColor: COLOR.surface100 }}>
      <View style={s.header}>
        <Text style={s.headerTitle}>Capture</Text>
        <Text style={s.headerSubtitle}>What are you recording?</Text>
      </View>

      <View style={s.tip}>
        <Icon name="search" size={16} color={COLOR.primary700} />
        <Text style={s.tipText}>
          Before capturing, check the map — there may already be an existing record nearby.
        </Text>
      </View>

      <View style={s.list}>
        <Tile icon="building" title="Building" subtitle="Update or verify a building record"
          onPress={() => onPick('building')} />
        <Tile icon="manhole" title="Manhole / Handhole" subtitle="Capture a chamber's location and condition"
          onPress={() => onPick('manhole')} />
        <Tile icon="road" title="Road / Street" subtitle="Record or verify street information"
          onPress={() => onPick('street')} />
        <Tile icon="route" title="Track Route" subtitle="Walk or drive and record a survey route"
          onPress={() => onPick('route')} />
        <Tile icon="photo" title="Photo" subtitle="Attach a photo to a building"
          onPress={() => onPick('building_photo')} />
      </View>
    </View>
  );
}

function Tile({ icon, title, subtitle, onPress, disabled, disabledNote }: {
  icon: IconName; title: string; subtitle: string; onPress?: () => void;
  disabled?: boolean; disabledNote?: string;
}) {
  return (
    <TouchableOpacity
      style={[s.tile, disabled && s.tileDisabled, isWeb && !disabled && ({ cursor: 'pointer' } as any)]}
      onPress={onPress} disabled={disabled} activeOpacity={0.7}
    >
      <View style={[s.tileIconWell, disabled && s.tileIconWellDisabled]}>
        <Icon name={icon} size={22} color={disabled ? COLOR.text500 : COLOR.primary900} />
      </View>
      <View style={{ flex: 1, minWidth: 0 }}>
        <Text style={[s.tileTitle, disabled && s.tileTitleDisabled]}>{title}</Text>
        <Text style={s.tileSubtitle} numberOfLines={2}>{subtitle}</Text>
      </View>
      {disabled ? (
        <Text style={s.comingSoon}>{disabledNote}</Text>
      ) : (
        <Icon name="chevronRight" size={18} color={COLOR.text500} />
      )}
    </TouchableOpacity>
  );
}

const s = StyleSheet.create({
  header: { backgroundColor: COLOR.primary900, paddingTop: 54, paddingBottom: SPACE.md, paddingHorizontal: SPACE.md },
  headerTitle: { ...TYPE.h2, fontSize: 26, color: '#fff' },
  headerSubtitle: { ...TYPE.body, fontSize: 14, color: 'rgba(244,246,249,0.85)', marginTop: 2 },
  tip: {
    flexDirection: 'row', alignItems: 'flex-start', gap: SPACE.sm,
    backgroundColor: '#EAF4FB', borderRadius: RADIUS.md, margin: SPACE.md, padding: SPACE.sm + 4,
  },
  tipText: { ...TYPE.small, flex: 1, color: COLOR.primary900 },
  list: { paddingHorizontal: SPACE.md, gap: SPACE.sm },
  tile: {
    flexDirection: 'row', alignItems: 'center', gap: SPACE.sm + 2,
    backgroundColor: COLOR.surface0, borderRadius: RADIUS.md, borderWidth: 1, borderColor: COLOR.borderCard,
    padding: SPACE.sm + 4, minHeight: MIN_TOUCH + 12,
  },
  tileDisabled: { opacity: 0.6 },
  tileIconWell: {
    width: 44, height: 44, borderRadius: RADIUS.md, backgroundColor: COLOR.neutralTint,
    alignItems: 'center', justifyContent: 'center', flexShrink: 0,
  },
  tileIconWellDisabled: { backgroundColor: COLOR.surface100 },
  tileTitle: { ...TYPE.bodyBold, fontSize: 15, color: COLOR.text900 },
  tileTitleDisabled: { color: COLOR.text500 },
  tileSubtitle: { ...TYPE.small, color: COLOR.text500, marginTop: 1 },
  comingSoon: { ...TYPE.small, fontSize: 11, color: COLOR.text500, fontWeight: '700' },
});
