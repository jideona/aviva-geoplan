// Touch-First List Item with swipe actions — Vol.4.1 §11. Applied to
// "Recent Captures" / "Pending Syncs". Replaces a persistent text "Delete"
// button with swipe-to-reveal actions, reducing visual clutter.
//
// Swipe left reveals a fixed Error-red background + delete action on the
// right edge. Swipe right reveals a Teal background + sync/check action.
// Accessibility note in §11: swipe needs a non-gesture fallback for switch
// control / assistive-tech users — long-press opens the same two actions in
// a BottomSheet instead of requiring a drag gesture.
import { useRef, useState } from 'react';
import { Animated, PanResponder, StyleSheet, Text, TouchableOpacity, View } from 'react-native';
import { COLOR, RADIUS, SPACE, TYPE, isWeb } from '../theme';
import BottomSheet from './BottomSheet';

const SWIPE_THRESHOLD = 88;

export default function SwipeableRow({
  onDelete, onSync, onPress, syncLabel = 'Sync now', children,
}: {
  onDelete: () => void;
  onSync?: () => void;
  /** Plain tap (not the long-press actions menu) — opens record detail. */
  onPress?: () => void;
  syncLabel?: string;
  children: React.ReactNode;
}) {
  const tx = useRef(new Animated.Value(0)).current;
  const [menuOpen, setMenuOpen] = useState(false);

  const responder = useRef(
    PanResponder.create({
      onMoveShouldSetPanResponder: (_, g) => Math.abs(g.dx) > 8 && Math.abs(g.dx) > Math.abs(g.dy),
      onPanResponderMove: (_, g) => tx.setValue(g.dx),
      onPanResponderRelease: (_, g) => {
        if (g.dx < -SWIPE_THRESHOLD) { onDelete(); return; }
        if (g.dx > SWIPE_THRESHOLD && onSync) { onSync(); }
        Animated.spring(tx, { toValue: 0, useNativeDriver: !isWeb }).start();
      },
    }),
  ).current;

  return (
    <View style={s.wrap}>
      {/* Right-edge reveal (swipe left) — delete */}
      <View style={[s.reveal, s.revealRight]}>
        <Text style={s.revealIcon}>🗑</Text>
      </View>
      {/* Left-edge reveal (swipe right) — sync */}
      {onSync && (
        <View style={[s.reveal, s.revealLeft]}>
          <Text style={s.revealIcon}>✓</Text>
        </View>
      )}
      <Animated.View
        {...responder.panHandlers}
        style={[s.row, { transform: [{ translateX: tx }] }]}
      >
        {/* Long-press fallback for non-gesture / switch-control input (§11 accessibility note). */}
        <TouchableOpacity activeOpacity={onPress ? 0.7 : 1} delayLongPress={450}
          onLongPress={() => setMenuOpen(true)} onPress={onPress} style={{ flex: 1 }}>
          {children}
        </TouchableOpacity>
      </Animated.View>

      <BottomSheet visible={menuOpen} onClose={() => setMenuOpen(false)} title="Capture actions">
        {onSync && (
          <TouchableOpacity style={s.menuItem} onPress={() => { setMenuOpen(false); onSync(); }}>
            <Text style={s.menuItemText}>{syncLabel}</Text>
          </TouchableOpacity>
        )}
        <TouchableOpacity style={s.menuItem} onPress={() => { setMenuOpen(false); onDelete(); }}>
          <Text style={[s.menuItemText, { color: COLOR.error }]}>Delete</Text>
        </TouchableOpacity>
      </BottomSheet>
    </View>
  );
}

const s = StyleSheet.create({
  wrap: { marginBottom: SPACE.sm, borderRadius: RADIUS.md, overflow: 'hidden' },
  row: { backgroundColor: COLOR.surface0 },
  reveal: {
    ...StyleSheet.absoluteFillObject,
    alignItems: 'center', justifyContent: 'center', width: 72,
  },
  revealRight: { right: 0, left: undefined, backgroundColor: COLOR.error, alignItems: 'flex-end', paddingRight: SPACE.lg },
  revealLeft: { left: 0, right: undefined, backgroundColor: COLOR.success500, alignItems: 'flex-start', paddingLeft: SPACE.lg },
  revealIcon: { color: '#fff', fontSize: 18 },
  menuItem: { paddingVertical: SPACE.md, borderBottomWidth: 1, borderBottomColor: COLOR.surface100 },
  menuItemText: { ...TYPE.bodyBold, color: COLOR.text900 },
});
