// New entry screen per the Claude Design redesign ("Field Survey App
// Redesign.dc.html", screen 0). Shown briefly on cold boot while the app
// initialises (fonts, local DB, stored auth) — App.tsx already has a real
// boot sequence to wait on; this just gives it a branded face instead of a
// bare spinner. Auto-advances via the `onDone` callback once App.tsx's own
// readiness flips true AND a minimum dwell time has passed, so the splash
// doesn't just flash for one frame on a fast reload.
import { useEffect } from 'react';
import { View, Text, StyleSheet, ActivityIndicator } from 'react-native';
import AvivaLogo from '../components/AvivaLogo';
import { COLOR, SPACE, TYPE, RADIUS, ELEVATION } from '../theme';

const MIN_DWELL_MS = 900;

export default function SplashScreen({ ready, onDone }: { ready: boolean; onDone: () => void }) {
  useEffect(() => {
    const start = Date.now();
    let cancelled = false;
    const tick = () => {
      if (cancelled) return;
      if (ready && Date.now() - start >= MIN_DWELL_MS) { onDone(); return; }
      setTimeout(tick, 100);
    };
    tick();
    return () => { cancelled = true; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [ready]);

  return (
    <View style={s.root}>
      <View style={[s.ring, s.ringOuter]} />
      <View style={[s.ring, s.ringInner]} />

      <View style={s.badge}>
        <AvivaLogo style={{ width: '100%', height: '100%' }} />
      </View>

      <View style={s.textBlock}>
        <Text style={s.title}>Aviva GeoPlan Survey</Text>
        <Text style={s.subtitle}>FIELD INFRASTRUCTURE CAPTURE</Text>
      </View>

      <View style={s.footer}>
        <ActivityIndicator color={COLOR.accent500} />
        <Text style={s.version}>v0.1.0</Text>
      </View>
    </View>
  );
}

const s = StyleSheet.create({
  root: { flex: 1, backgroundColor: COLOR.primary900, alignItems: 'center', justifyContent: 'center', gap: SPACE.lg, overflow: 'hidden' },
  ring: { position: 'absolute', borderRadius: RADIUS.full, borderWidth: 1 },
  ringOuter: { width: 340, height: 340, borderColor: 'rgba(255,255,255,0.06)' },
  ringInner: { width: 220, height: 220, borderColor: 'rgba(255,255,255,0.08)' },
  badge: {
    width: 96, height: 96, borderRadius: 22, backgroundColor: COLOR.surface0,
    alignItems: 'center', justifyContent: 'center', padding: SPACE.md, ...ELEVATION[3],
  },
  textBlock: { alignItems: 'center', gap: SPACE.xs },
  title: { ...TYPE.h2, color: '#fff' },
  subtitle: { ...TYPE.mono, fontSize: 12, letterSpacing: 2, color: 'rgba(244,246,249,0.55)' },
  footer: { position: 'absolute', bottom: 64, alignItems: 'center', gap: SPACE.sm },
  version: { ...TYPE.mono, fontSize: 11, color: 'rgba(244,246,249,0.45)' },
});
