// Shown instead of the real app whenever a session is already signed in
// (valid refresh token) but Face ID / Touch ID lock is turned on — at cold
// boot and whenever App.tsx sees the app return from the background. Prompts
// immediately on mount so most surveyors never actually see this screen for
// more than a blink.
import { useEffect, useState } from 'react';
import { View, Text, TouchableOpacity, StyleSheet, ActivityIndicator } from 'react-native';
import { authenticateBiometric, supportedTypeLabel } from '../biometrics';
import { logout } from '../auth';
import AvivaLogo from '../components/AvivaLogo';
import { COLOR, SPACE, RADIUS, ELEVATION, TYPE } from '../theme';

export default function LockScreen({ onUnlocked, onUsePassword }: {
  onUnlocked: () => void;
  onUsePassword: () => void;
}) {
  const [label, setLabel] = useState('device biometrics');
  const [busy, setBusy] = useState(false);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    let live = true;
    (async () => {
      const l = await supportedTypeLabel();
      if (live) setLabel(l);
      await prompt();
    })();
    return () => { live = false; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function prompt() {
    setBusy(true); setFailed(false);
    const ok = await authenticateBiometric('Unlock Aviva GeoPlan');
    setBusy(false);
    if (ok) onUnlocked(); else setFailed(true);
  }

  async function usePasswordInstead() {
    // Deliberately clears the session rather than just dismissing the lock —
    // "use password instead" has to mean a real password check, not a way
    // around the lock screen.
    await logout();
    onUsePassword();
  }

  return (
    <View style={s.root}>
      <View style={s.badge}><AvivaLogo style={{ width: '100%', height: '100%' }} /></View>
      <Text style={s.title}>GeoPlan is locked</Text>
      <Text style={s.sub}>Use {label} to continue where you left off.</Text>

      {busy && <ActivityIndicator color="#fff" style={{ marginTop: SPACE.lg }} />}
      {failed && !busy && <Text style={s.err}>Not recognized — try again.</Text>}

      <TouchableOpacity style={s.unlockBtn} onPress={prompt} disabled={busy}>
        <Text style={s.unlockText}>Unlock with {label}</Text>
      </TouchableOpacity>
      <TouchableOpacity onPress={usePasswordInstead} hitSlop={{ top: 8, bottom: 8, left: 8, right: 8 }}>
        <Text style={s.passwordLink}>Use email and password instead</Text>
      </TouchableOpacity>
    </View>
  );
}

const s = StyleSheet.create({
  root: { flex: 1, backgroundColor: COLOR.primary900, alignItems: 'center', justifyContent: 'center', padding: SPACE.xl },
  badge: {
    width: 72, height: 72, borderRadius: RADIUS.lg, backgroundColor: COLOR.surface0,
    alignItems: 'center', justifyContent: 'center', padding: SPACE.sm + 4, marginBottom: SPACE.lg, ...ELEVATION[2],
  },
  title: { ...TYPE.h3, color: '#fff', marginBottom: SPACE.xs },
  sub: { ...TYPE.body, color: 'rgba(255,255,255,0.75)', textAlign: 'center', marginBottom: SPACE.sm },
  err: { ...TYPE.small, color: '#FFB4A8', marginTop: SPACE.sm },
  unlockBtn: {
    backgroundColor: COLOR.accent500, borderRadius: RADIUS.md, height: 48, paddingHorizontal: SPACE.xl,
    alignItems: 'center', justifyContent: 'center', marginTop: SPACE.lg, marginBottom: SPACE.lg,
  },
  unlockText: { ...TYPE.bodyBold, fontSize: 15, color: '#fff' },
  passwordLink: { ...TYPE.small, color: 'rgba(255,255,255,0.85)', textDecorationLine: 'underline' },
});
