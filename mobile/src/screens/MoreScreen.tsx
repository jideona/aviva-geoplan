// More tab — menu list, exact row order from the design bundle: Buildings,
// Manholes & Handholes, Roads & Routes, Field Activity, Pending & Drafts,
// Needs Attention, QA Review (Admin only), Project, Switch Project,
// Settings, Sign Out. Most of these rows don't have a real destination yet
// (dedicated category lists are PR 8, Field Activity is PR 10, Pending &
// Drafts is PR 9, QA Review is PR 12, admin gating is PR 3) — shown,
// disabled, "Coming soon" rather than hidden, so the menu's shape matches
// the design now. Switch Project and Sign Out are real, existing actions
// and are wired immediately.
import { View, Text, TouchableOpacity, StyleSheet, ScrollView } from 'react-native';
import { COLOR, SPACE, RADIUS, TYPE, MIN_TOUCH, isWeb } from '../theme';
import { Icon, type IconName } from '../components/Icon';

export default function MoreScreen({ onOpenData, onSwitchProject, onLogout }: {
  onOpenData: () => void;
  onSwitchProject: () => void;
  onLogout: () => void;
}) {
  return (
    <View style={{ flex: 1, backgroundColor: COLOR.surface100 }}>
      <View style={s.header}>
        <Text style={s.headerTitle}>More</Text>
      </View>
      <ScrollView contentContainerStyle={s.list}>
        <Row icon="building" label="Buildings" onPress={onOpenData} />
        <Row icon="manhole" label="Manholes & Handholes" onPress={onOpenData} />
        <Row icon="road" label="Roads & Routes" comingSoon />
        <Row icon="fieldActivity" label="Field Activity" comingSoon />
        <Row icon="pendingDrafts" label="Pending & Drafts" comingSoon />
        <Row icon="flagged" label="Needs Attention" comingSoon />
        <Row icon="qaReview" label="QA Review" sublabel="Admin only" comingSoon />

        <View style={s.divider} />

        <Row icon="project" label="Project" comingSoon />
        <Row icon="switchProject" label="Switch Project" onPress={onSwitchProject} />
        <Row icon="settings" label="Settings" comingSoon />

        <View style={s.divider} />

        <Row icon="signOut" label="Sign Out" onPress={onLogout} destructive />
      </ScrollView>
    </View>
  );
}

function Row({ icon, label, sublabel, onPress, comingSoon, destructive }: {
  icon: IconName; label: string; sublabel?: string; onPress?: () => void;
  comingSoon?: boolean; destructive?: boolean;
}) {
  const disabled = comingSoon || !onPress;
  return (
    <TouchableOpacity
      style={[s.row, disabled && s.rowDisabled, isWeb && !disabled && ({ cursor: 'pointer' } as any)]}
      onPress={onPress} disabled={disabled} activeOpacity={0.7}
    >
      <Icon name={icon} size={20} color={disabled ? COLOR.text500 : destructive ? COLOR.error : COLOR.primary900} />
      <View style={{ flex: 1, minWidth: 0 }}>
        <Text style={[s.rowLabel, disabled && s.rowLabelDisabled, destructive && { color: COLOR.error }]}>
          {label}
        </Text>
        {!!sublabel && <Text style={s.rowSublabel}>{sublabel}</Text>}
      </View>
      {comingSoon ? (
        <Text style={s.comingSoon}>Coming soon</Text>
      ) : onPress ? (
        <Icon name="chevronRight" size={16} color={COLOR.text500} />
      ) : null}
    </TouchableOpacity>
  );
}

const s = StyleSheet.create({
  header: { backgroundColor: COLOR.primary900, paddingTop: 54, paddingBottom: SPACE.md, paddingHorizontal: SPACE.md },
  headerTitle: { ...TYPE.h2, fontSize: 26, color: '#fff' },
  list: { paddingHorizontal: SPACE.md, paddingVertical: SPACE.sm },
  row: {
    flexDirection: 'row', alignItems: 'center', gap: SPACE.sm + 2,
    backgroundColor: COLOR.surface0, borderRadius: RADIUS.md, borderWidth: 1, borderColor: COLOR.borderCard,
    paddingHorizontal: SPACE.sm + 4, minHeight: MIN_TOUCH + 4, marginBottom: SPACE.xs + 2,
  },
  rowDisabled: { opacity: 0.55 },
  rowLabel: { ...TYPE.bodyBold, fontSize: 15, color: COLOR.text900 },
  rowLabelDisabled: { color: COLOR.text500 },
  rowSublabel: { ...TYPE.small, fontSize: 11, color: COLOR.text500 },
  comingSoon: { ...TYPE.small, fontSize: 11, color: COLOR.text500, fontWeight: '700' },
  divider: { height: 1, backgroundColor: COLOR.borderCard, marginVertical: SPACE.sm },
});
