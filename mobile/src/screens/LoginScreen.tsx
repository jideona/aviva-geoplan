import { useEffect, useState } from 'react';
import { View, Text, TextInput, TouchableOpacity, StyleSheet, ActivityIndicator, ScrollView } from 'react-native';
import NetInfo from '@react-native-community/netinfo';
import { login } from '../auth';
import { getApiBase, setApiBase } from '../config';
import { notify } from '../notify';
import AvivaLogo from '../components/AvivaLogo';
import { COLOR, SPACE, RADIUS, ELEVATION, TYPE, MIN_TOUCH, isWeb } from '../theme';

export default function LoginScreen({ onDone }: { onDone: () => void }) {
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [showPassword, setShowPassword] = useState(false);
  const [server, setServer] = useState(getApiBase());
  const [showServer, setShowServer] = useState(false);
  const [testing, setTesting] = useState(false);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [online, setOnline] = useState(true);
  const [focus, setFocus] = useState<'email' | 'password' | null>(null);

  useEffect(() => {
    const unsub = NetInfo.addEventListener((st) => setOnline(!!st.isConnected));
    return unsub;
  }, []);

  async function submit() {
    setBusy(true); setErr(null);
    try { await setApiBase(server); await login(email.trim(), password); onDone(); }
    catch (e: any) { setErr(String(e?.message ?? e)); }
    finally { setBusy(false); }
  }

  async function testServer() {
    setTesting(true);
    try {
      await setApiBase(server);
      const res = await fetch(`${getApiBase()}/api/v1/health`);
      const body = await res.text();
      notify('Server test', res.ok ? `Reachable ✓  (${body})` : `HTTP ${res.status}`);
    } catch (e: any) {
      notify('Server test', `Could not reach server.\n${String(e?.message ?? e)}`);
    } finally { setTesting(false); }
  }

  return (
    <ScrollView style={s.root} contentContainerStyle={{ flexGrow: 1 }} keyboardShouldPersistTaps="handled">
      <View style={s.header}>
        <View style={s.badge}><AvivaLogo style={{ width: '100%', height: '100%' }} /></View>
        <Text style={s.headerTitle}>Sign in to GeoPlan</Text>
      </View>

      <View style={s.body}>
        <Text style={s.label}>Email</Text>
        <TextInput style={[s.input, focus === 'email' && s.inputFocused]}
          placeholder="you@avivanetworx.com" placeholderTextColor={COLOR.text500}
          autoCapitalize="none" autoCorrect={false} keyboardType="email-address"
          onFocus={() => setFocus('email')} onBlur={() => setFocus(null)}
          value={email} onChangeText={setEmail} />

        <Text style={s.label}>Password</Text>
        <View style={[s.passwordRow, focus === 'password' && s.inputFocused]}>
          <TextInput style={s.passwordInput} placeholder="········" placeholderTextColor={COLOR.text500}
            secureTextEntry={!showPassword} value={password} onChangeText={setPassword}
            onFocus={() => setFocus('password')} onBlur={() => setFocus(null)} />
          <TouchableOpacity style={s.eyeBtn} onPress={() => setShowPassword((v) => !v)}>
            <Text style={s.eyeText}>{showPassword ? 'Hide' : 'Show'}</Text>
          </TouchableOpacity>
        </View>

        <TouchableOpacity style={s.forgotRow}
          onPress={() => notify('Forgot password', 'Password resets aren’t self-service yet — contact your field coordinator to have it reset.')}
          hitSlop={{ top: 12, bottom: 12, left: 8, right: 8 }}>
          <Text style={s.forgotText}>Forgot password?</Text>
        </TouchableOpacity>

        {err && <Text style={s.err}>{err}</Text>}

        <TouchableOpacity style={[s.signInBtn, (busy || !online) && { opacity: 0.6 }, isWeb && ({ cursor: 'pointer' } as any)]}
          activeOpacity={0.85} onPress={submit} disabled={busy || !online}>
          {busy ? <ActivityIndicator color="#fff" /> : <Text style={s.signInText}>Sign In</Text>}
        </TouchableOpacity>

        {/* Biometrics can't log you in without a password to check against —
            it lives as an app-lock on the Dashboard menu once you're signed
            in, not here. See src/biometrics.ts. */}

        {!online && (
          <View style={s.offlineBanner}>
            <View style={s.offlineDot} />
            <Text style={s.offlineText}>You're offline — sign-in needs a connection. If you've signed in on this device before, you won't need to sign in again; just reopen the app.</Text>
          </View>
        )}

        <TouchableOpacity onPress={() => setShowServer((v) => !v)} style={{ marginTop: SPACE.lg, minHeight: MIN_TOUCH, justifyContent: 'center' }}>
          <Text style={s.serverToggle}>{showServer ? 'Hide server settings' : 'Server settings'}</Text>
        </TouchableOpacity>
        {showServer && (
          <View style={s.serverBox}>
            <Text style={s.serverLabel}>API ADDRESS</Text>
            <TextInput style={s.serverInput} placeholder="http://192.168.1.236:8000" placeholderTextColor={COLOR.text500}
              autoCapitalize="none" autoCorrect={false} keyboardType="url"
              value={server} onChangeText={setServer} />
            <TouchableOpacity style={s.testBtn} onPress={testServer} disabled={testing}>
              {testing ? <ActivityIndicator color={COLOR.primary700} /> : <Text style={s.testText}>Test connection</Text>}
            </TouchableOpacity>
            <Text style={s.hint}>Use your server's LAN address (e.g. http://192.168.1.236:8000). Saved on this device.</Text>
          </View>
        )}
      </View>

      <View style={s.footer}>
        <Text style={s.footerText}>Need access? </Text>
        <Text style={s.footerLink}>Contact your field coordinator</Text>
      </View>
    </ScrollView>
  );
}

const s = StyleSheet.create({
  root: { flex: 1, backgroundColor: COLOR.surface100 },
  header: { backgroundColor: COLOR.primary900, paddingTop: 64, paddingBottom: SPACE.xl, paddingHorizontal: SPACE.lg, alignItems: 'center', gap: SPACE.md - 2 },
  badge: { width: 60, height: 60, borderRadius: RADIUS.lg, backgroundColor: COLOR.surface0, alignItems: 'center', justifyContent: 'center', padding: SPACE.sm + 2, ...ELEVATION[2] },
  headerTitle: { ...TYPE.h3, fontSize: 20, color: '#fff' },
  body: { flex: 1, padding: SPACE.lg - 4 },
  label: { ...TYPE.mono, fontSize: 11, letterSpacing: 1, color: COLOR.text500, textTransform: 'uppercase', marginBottom: SPACE.xs + 2, marginTop: SPACE.md - 4 },
  input: { ...TYPE.body, backgroundColor: COLOR.surface0, borderRadius: RADIUS.sm, padding: SPACE.md - 4, borderWidth: 1, borderColor: COLOR.borderDefault, color: COLOR.text900, minHeight: MIN_TOUCH },
  passwordRow: { flexDirection: 'row', alignItems: 'center', backgroundColor: COLOR.surface0, borderRadius: RADIUS.sm, borderWidth: 1, borderColor: COLOR.borderDefault, minHeight: MIN_TOUCH },
  inputFocused: { borderColor: COLOR.primary500, shadowColor: COLOR.primary500, shadowOffset: { width: 0, height: 0 }, shadowOpacity: 0.12, shadowRadius: 2, elevation: 0 },
  passwordInput: { ...TYPE.body, flex: 1, padding: SPACE.md - 4, color: COLOR.text900 },
  eyeBtn: { minWidth: MIN_TOUCH, minHeight: MIN_TOUCH, alignItems: 'center', justifyContent: 'center', paddingHorizontal: SPACE.sm },
  eyeText: { ...TYPE.small, fontWeight: '700', color: COLOR.primary700 },
  forgotRow: { alignSelf: 'flex-end', marginTop: SPACE.sm, marginBottom: SPACE.md },
  forgotText: { ...TYPE.small, fontWeight: '500', color: COLOR.primary700 },
  err: { ...TYPE.small, color: COLOR.error, marginBottom: SPACE.sm },
  signInBtn: { backgroundColor: COLOR.accent500, borderRadius: RADIUS.md, height: 48, alignItems: 'center', justifyContent: 'center', marginBottom: SPACE.md },
  signInText: { ...TYPE.bodyBold, fontSize: 15, color: '#fff' },
  offlineBanner: { marginTop: SPACE.lg, padding: SPACE.md - 4, backgroundColor: '#FDECE5', borderRadius: RADIUS.md, flexDirection: 'row', gap: SPACE.sm + 2, alignItems: 'flex-start' },
  offlineDot: { width: 8, height: 8, borderRadius: 4, backgroundColor: COLOR.accent500, marginTop: 5, flexShrink: 0 },
  offlineText: { ...TYPE.small, fontSize: 12, lineHeight: 17, color: COLOR.accent700, flex: 1 },
  serverToggle: { ...TYPE.small, color: COLOR.primary700, textAlign: 'center' },
  serverBox: { marginTop: SPACE.sm, backgroundColor: COLOR.surface0, borderRadius: RADIUS.md, padding: SPACE.md, borderWidth: 1, borderColor: COLOR.borderDefault },
  serverLabel: { ...TYPE.mono, fontSize: 10, letterSpacing: 1.5, color: COLOR.text500, marginBottom: SPACE.sm },
  serverInput: { ...TYPE.body, backgroundColor: COLOR.surface100, borderRadius: RADIUS.sm, padding: SPACE.sm + 2, color: COLOR.text900 },
  testBtn: { borderWidth: 1, borderColor: COLOR.primary700, borderRadius: RADIUS.md, padding: SPACE.sm + 2, alignItems: 'center', marginTop: SPACE.sm, minHeight: MIN_TOUCH, justifyContent: 'center' },
  testText: { ...TYPE.bodyBold, fontSize: 14, color: COLOR.primary700 },
  hint: { ...TYPE.small, fontSize: 11, color: COLOR.text500, marginTop: SPACE.sm },
  footer: { flexDirection: 'row', justifyContent: 'center', paddingVertical: SPACE.lg, flexWrap: 'wrap' },
  footerText: { ...TYPE.small, fontSize: 12, color: COLOR.text500 },
  footerLink: { ...TYPE.small, fontSize: 12, fontWeight: '700', color: COLOR.primary700 },
});
