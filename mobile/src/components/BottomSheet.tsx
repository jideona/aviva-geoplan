// Standard Bottom Sheet — Vol.4.1 §08. Replaces full-screen page navigation
// for data entry (adding a building, updating a manhole) so the surveyor
// stays anchored to whatever's behind it (map or home) instead of losing
// that context on every capture.
//
// Spec: Surface/0 fill, radius.lg on the top two corners only, elevation.4
// (sits above FABs — elevation.3 — in the stacking order). Drag handle pill
// centred at top. Navy scrim at 40% opacity behind it; tapping the scrim or
// swiping down dismisses. No external gesture library — PanResponder (core
// React Native, works on native and react-native-web alike) is enough for a
// single vertical drag-to-dismiss gesture.
import { useRef } from 'react';
import {
  Animated, PanResponder, ScrollView, StyleSheet, Text, TouchableWithoutFeedback, View,
} from 'react-native';
import { COLOR, RADIUS, ELEVATION, SPACE, TYPE, isWeb } from '../theme';

export default function BottomSheet({
  visible, onClose, title, children, maxHeight = '80%',
}: {
  visible: boolean;
  onClose: () => void;
  title?: string;
  children: React.ReactNode;
  maxHeight?: number | string;
}) {
  const pan = useRef(new Animated.Value(0)).current;
  const responder = useRef(
    PanResponder.create({
      onStartShouldSetPanResponder: () => true,
      onMoveShouldSetPanResponder: (_, g) => Math.abs(g.dy) > 6,
      onPanResponderMove: (_, g) => { if (g.dy > 0) pan.setValue(g.dy); },
      onPanResponderRelease: (_, g) => {
        if (g.dy > 120 || g.vy > 1.2) { onClose(); }
        Animated.spring(pan, { toValue: 0, useNativeDriver: !isWeb }).start();
      },
    }),
  ).current;

  if (!visible) return null;

  return (
    <View style={StyleSheet.absoluteFill} pointerEvents="box-none">
      {/* Scrim — Navy overlay at 40% opacity. Tap to dismiss. */}
      <TouchableWithoutFeedback onPress={onClose}>
        <View style={s.scrim} />
      </TouchableWithoutFeedback>

      <Animated.View
        style={[s.sheet, { maxHeight: maxHeight as any, transform: [{ translateY: pan }] }]}
        {...responder.panHandlers}
      >
        <View style={s.handle} />
        {title ? <Text style={s.title}>{title}</Text> : null}
        <ScrollView style={s.content} contentContainerStyle={{ paddingBottom: SPACE.md }}
          keyboardShouldPersistTaps="handled">
          {children}
        </ScrollView>
      </Animated.View>
    </View>
  );
}

const s = StyleSheet.create({
  scrim: {
    ...StyleSheet.absoluteFillObject,
    backgroundColor: COLOR.primary900,
    opacity: 0.4,
  },
  sheet: {
    position: 'absolute', left: 0, right: 0, bottom: 0,
    backgroundColor: COLOR.surface0,
    borderTopLeftRadius: RADIUS.lg,
    borderTopRightRadius: RADIUS.lg,
    ...ELEVATION[4],
    paddingBottom: SPACE.lg,
  },
  handle: {
    alignSelf: 'center',
    width: 32, height: 4, borderRadius: RADIUS.full,
    backgroundColor: COLOR.surface100,
    marginTop: SPACE.sm, marginBottom: SPACE.xs,
  },
  title: { ...TYPE.h3, color: COLOR.text900, paddingHorizontal: SPACE.md, marginTop: SPACE.xs, marginBottom: SPACE.sm },
  content: { paddingHorizontal: SPACE.md },
});
