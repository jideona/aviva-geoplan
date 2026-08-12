import { useEffect, useRef, useState } from 'react';
import { View, StyleSheet, ActivityIndicator, Platform, AppState, type AppStateStatus } from 'react-native';
import { StatusBar } from 'expo-status-bar';
import * as SplashScreenNative from 'expo-splash-screen';
import { useFonts, DMSans_400Regular, DMSans_700Bold } from '@expo-google-fonts/dm-sans';
import { SpaceMono_400Regular } from '@expo-google-fonts/space-mono';
import { initDb, kvGet } from './src/db';
import { loadApiBase } from './src/config';
import { loadTokens, isAuthed } from './src/auth';
import { isBiometricLockEnabled, hasBiometricHardware } from './src/biometrics';
import SplashScreen from './src/screens/SplashScreen';
import LockScreen from './src/screens/LockScreen';
import LoginScreen from './src/screens/LoginScreen';
import ProjectListScreen from './src/screens/ProjectListScreen';
import DashboardScreen from './src/screens/DashboardScreen';
import ManholeScreen from './src/screens/ManholeScreen';
import BuildingScreen from './src/screens/BuildingScreen';
import BuildingPhotoScreen from './src/screens/BuildingPhotoScreen';
import MapScreen from './src/screens/MapScreen';
import BottomSheet from './src/components/BottomSheet';
import { COLOR } from './src/theme';

type Screen = 'projects' | 'dashboard' | 'map';
type Sheet = 'manhole' | 'building' | 'building_photo' | null;

// Keep the native splash (app.json's expo-splash-screen config) on screen
// through font loading + the async boot sequence below, instead of it
// auto-hiding on first frame and leaving a blank flash before either is
// ready. No-op on web, where there is no native splash to hold. Our own
// branded SplashScreen (below) takes over immediately after, on every
// platform including web, per the Claude Design redesign.
if (Platform.OS !== 'web') {
  SplashScreenNative.preventAutoHideAsync().catch(() => {});
}

export default function App() {
  const [fontsLoaded] = useFonts({ DMSans_400Regular, DMSans_700Bold, SpaceMono_400Regular });
  const [booted, setBooted] = useState(false);
  const [authed, setAuthed] = useState(false);
  const [splashDone, setSplashDone] = useState(false);
  const [screen, setScreen] = useState<Screen>('projects');
  const [sheet, setSheet] = useState<Sheet>(null);
  // null = not evaluated yet (stay on the boot spinner instead of flashing
  // real content before we know whether a lock applies); true/false once known.
  const [locked, setLocked] = useState<boolean | null>(null);
  const bioLockOnRef = useRef(false);
  const appStateRef = useRef(AppState.currentState);

  async function evaluateLock(): Promise<boolean> {
    const [enabled, hw] = await Promise.all([isBiometricLockEnabled(), hasBiometricHardware()]);
    const on = enabled && hw;
    bioLockOnRef.current = on;
    return on;
  }

  useEffect(() => {
    (async () => {
      await initDb();
      await loadApiBase();
      await loadTokens();
      const ok = isAuthed();
      setAuthed(ok);
      if (ok) {
        const pid = await kvGet('projectId');
        setScreen(pid ? 'dashboard' : 'projects');
        setLocked(await evaluateLock());
      } else {
        setLocked(false);
      }
      setBooted(true);
    })();
    // Registers the app-shell service worker so the installed PWA still
    // opens (from cache) with no signal. No-op on native.
    if (Platform.OS === 'web' && typeof navigator !== 'undefined' && 'serviceWorker' in navigator) {
      navigator.serviceWorker.register('/sw.js').catch(() => {});
    }
  }, []);

  // Re-lock whenever the app comes back from the background — the case a
  // cold-boot check alone misses (phone put in a pocket mid-session, picked
  // up by someone else, app still running). No-op on web, where there's no
  // meaningful "backgrounded" state and biometrics are unavailable anyway.
  useEffect(() => {
    if (Platform.OS === 'web') return;
    const sub = AppState.addEventListener('change', (next: AppStateStatus) => {
      const prev = appStateRef.current;
      appStateRef.current = next;
      const cameToForeground = /inactive|background/.test(prev) && next === 'active';
      if (cameToForeground && authed && bioLockOnRef.current) setLocked(true);
    });
    return () => sub.remove();
  }, [authed]);

  useEffect(() => {
    if (booted && fontsLoaded && Platform.OS !== 'web') {
      SplashScreenNative.hideAsync().catch(() => {});
    }
  }, [booted, fontsLoaded]);

  const ready = booted && fontsLoaded;

  async function afterLogin() {
    setAuthed(true);
    setLocked(false);
    await evaluateLock(); // sync bioLockOnRef for future backgrounding, without re-locking right now
    const pid = await kvGet('projectId');
    setScreen(pid ? 'dashboard' : 'projects');
  }

  function handleLogout() {
    setAuthed(false);
    setLocked(false);
    bioLockOnRef.current = false;
  }

  // Design System Vol.4.1 §12.4 "Desktop Constraint": on a wide (desktop/NOC)
  // viewport, the app shell should stay at a mobile-phone proportion rather
  // than stretching full width. That CSS rule targets #app-root — this View
  // becomes that element on web via nativeID, so one wrapper satisfies both
  // the constraint (CSS injected in scripts/patch-pwa-html.js) and gives
  // every screen a single, consistent root regardless of auth/boot state.
  return (
    <View style={s.root} nativeID={Platform.OS === 'web' ? 'app-root' : undefined}>
      {!splashDone ? (
        <SplashScreen ready={ready} onDone={() => setSplashDone(true)} />
      ) : !ready || locked === null ? (
        <View style={s.center}><ActivityIndicator color={COLOR.primary900} /></View>
      ) : !authed ? (
        <><StatusBar style="dark" /><LoginScreen onDone={afterLogin} /></>
      ) : locked ? (
        <LockScreen onUnlocked={() => setLocked(false)} onUsePassword={handleLogout} />
      ) : (
        <>
          <StatusBar style="light" />
          {screen === 'projects' && (
            <ProjectListScreen
              onPicked={() => setScreen('dashboard')}
              onLogout={handleLogout}
            />
          )}
          {screen === 'dashboard' && (
            <DashboardScreen
              onOpenMap={() => setScreen('map')}
              onCapture={(kind) => setSheet(kind)}
              onSwitchProject={() => setScreen('projects')}
              onLogout={handleLogout}
              onBioLockChanged={(on) => { bioLockOnRef.current = on; }}
            />
          )}
          {screen === 'map' && (
            <MapScreen onBack={() => setScreen('dashboard')} />
          )}

          <BottomSheet visible={sheet === 'manhole'} onClose={() => setSheet(null)} title="Capture manhole">
            <ManholeScreen onSaved={() => setSheet(null)} />
          </BottomSheet>
          <BottomSheet visible={sheet === 'building'} onClose={() => setSheet(null)} title="Update building">
            <BuildingScreen onSaved={() => setSheet(null)} onCancel={() => setSheet(null)} />
          </BottomSheet>
          <BottomSheet visible={sheet === 'building_photo'} onClose={() => setSheet(null)} title="Building photo">
            <BuildingPhotoScreen onSaved={() => setSheet(null)} />
          </BottomSheet>
        </>
      )}
    </View>
  );
}

const s = StyleSheet.create({
  root: { flex: 1, backgroundColor: COLOR.surface100 },
  center: { flex: 1, justifyContent: 'center', alignItems: 'center' },
});
