import { useEffect, useRef, useState } from 'react';
import { View, StyleSheet, ActivityIndicator, Platform, AppState, type AppStateStatus } from 'react-native';
import { StatusBar } from 'expo-status-bar';
import * as SplashScreenNative from 'expo-splash-screen';
import { useFonts, DMSans_400Regular, DMSans_700Bold } from '@expo-google-fonts/dm-sans';
import { SpaceMono_400Regular } from '@expo-google-fonts/space-mono';
import { initDb, kvGet } from './src/db';
import { runSync } from './src/sync';
import type { DetailItem } from './src/components/RecordDetail';
import { loadApiBase } from './src/config';
import { loadTokens, isAuthed } from './src/auth';
import { loadCachedPermissions, refreshPermissions, clearPermissions } from './src/permissions';
import { isBiometricLockEnabled, hasBiometricHardware } from './src/biometrics';
import { useAutoSync } from './src/autoSync';
import SplashScreen from './src/screens/SplashScreen';
import LockScreen from './src/screens/LockScreen';
import LoginScreen from './src/screens/LoginScreen';
import ProjectListScreen from './src/screens/ProjectListScreen';
import DashboardScreen from './src/screens/DashboardScreen';
import ManholeScreen from './src/screens/ManholeScreen';
import BuildingScreen from './src/screens/BuildingScreen';
import BuildingPhotoScreen from './src/screens/BuildingPhotoScreen';
import RoadScreen from './src/screens/RoadScreen';
import RouteCaptureScreen from './src/screens/RouteCaptureScreen';
import MapScreen from './src/screens/MapScreen';
import UploadedDataScreen from './src/screens/UploadedDataScreen';
import ProjectDataScreen from './src/screens/ProjectDataScreen';
import FieldActivityScreen from './src/screens/FieldActivityScreen';
import CaptureScreen from './src/screens/CaptureScreen';
import MoreScreen from './src/screens/MoreScreen';
import BottomSheet from './src/components/BottomSheet';
import BottomNav, { type TabName } from './src/components/BottomNav';
import { COLOR } from './src/theme';

type Screen = 'projects' | 'app';
type Sheet = 'manhole' | 'building' | 'building_photo' | 'street' | 'route' | null;

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
  // The persistent 5-tab shell (Home/Map/Capture/Data/More) — only relevant
  // once screen === 'app' (a project is picked). Replaces the old
  // screen-enum push/pop between 'dashboard'/'map'/'uploaded'.
  const [tab, setTab] = useState<TabName>('home');
  const [sheet, setSheet] = useState<Sheet>(null);
  const [morePage, setMorePage] = useState<'activity' | 'pending' | null>(null);
  const [dataTarget, setDataTarget] = useState<{
    kind?: 'buildings' | 'manholes' | 'streets' | 'routes' | 'building_photos';
    filter?: 'all' | 'mine' | 'recent' | 'attention';
  } | null>(null);

  const [editTarget, setEditTarget] = useState<{
    item: DetailItem;
    server: any;
  } | null>(null);

  const [dataRefreshKey, setDataRefreshKey] = useState(0);
  // Set by the Dashboard's "Resume draft" quick action, alongside opening
  // the 'building' sheet — cleared whenever that sheet is opened normally
  // or closed, so a stale target never lingers into the next open.
  const [resumeDraft, setResumeDraft] = useState<{ buildingId: string; code: string | null } | null>(null);
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
      // Cached roles/permissions first, for instant offline-safe display;
      // a fresh /auth/me follows in the background so a stale cache never
      // blocks boot (see permissions.ts's refresh policy).
      await loadCachedPermissions();
      if (ok) {
        const pid = await kvGet('projectId');
        setScreen(pid ? 'app' : 'projects');
        setLocked(await evaluateLock());
        refreshPermissions();
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
      if (cameToForeground && authed) {
        if (bioLockOnRef.current) setLocked(true);
        refreshPermissions(); // roles/permissions may have changed while backgrounded
      }
    });
    return () => sub.remove();
  }, [authed]);

  useEffect(() => {
    if (booted && fontsLoaded && Platform.OS !== 'web') {
      SplashScreenNative.hideAsync().catch(() => {});
    }
  }, [booted, fontsLoaded]);

  const ready = booted && fontsLoaded;

  // Uploads queued captures the moment a connection is available, instead
  // of waiting for the surveyor to open a screen and tap Sync now. Enabled
  // for the lifetime of the login (not gated on the lock screen — a locked
  // phone still has a live network connection and queued work worth
  // sending), disabled again on logout.
  useAutoSync(authed);

  async function afterLogin() {
    setAuthed(true);
    setLocked(false);
    await evaluateLock(); // sync bioLockOnRef for future backgrounding, without re-locking right now
    await refreshPermissions(); // fresh roles/permissions for the account that just signed in, before any screen renders
    const pid = await kvGet('projectId');
    setScreen(pid ? 'app' : 'projects');
    setTab('home');
  }

  function handleLogout() {
    setAuthed(false);
    setLocked(false);
    bioLockOnRef.current = false;
    clearPermissions(); // don't leave the next signed-in account seeing a stale prior account's cache
  }

  function openCapture(kind: 'manhole' | 'building' | 'building_photo' | 'street' | 'route') {
    setEditTarget(null);
    setResumeDraft(null);
    setSheet(kind);
  }

  function openEditRecord(item: DetailItem, server: any) {
    const byKind: Record<string, Sheet> = {
      building: 'building',
      manhole: 'manhole',
      building_photo: 'building_photo',
      street: 'street',
      route: 'route',
    };
    const next = byKind[item.kind] ?? null;
    if (!next) return;
    setEditTarget({ item, server });
    setResumeDraft(null);
    setSheet(next);
  }

  function finishFieldSave() {
    setSheet(null);
    setResumeDraft(null);
    setEditTarget(null);
    setDataRefreshKey((v) => v + 1);

    void (async () => {
      const pid = await kvGet('projectId');
      if (!pid) return;
      try {
        await runSync(pid);
      } catch {
        // Offline field updates stay queued safely.
      } finally {
        setDataRefreshKey((v) => v + 1);
      }
    })();
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
              onPicked={() => { setScreen('app'); setTab('home'); }}
              onLogout={handleLogout}
            />
          )}
          {screen === 'app' && (
            <View style={{ flex: 1 }}>
              <View style={{ flex: 1 }}>
                {tab === 'home' && (
                  <DashboardScreen
                    onOpenMap={() => setTab('map')}
                    onCapture={openCapture}
                    onResumeDraft={(d) => { setResumeDraft(d); setSheet('building'); }}
                    onOpenUploadedData={(target) => {
                      setDataTarget(target ?? null);
                      setTab('data');
                    }}
                    onSwitchProject={() => setScreen('projects')}
                    onLogout={handleLogout}
                    onBioLockChanged={(on) => { bioLockOnRef.current = on; }}
                  />
                )}
                {tab === 'map' && (
                  <MapScreen onBack={() => setTab('home')} />
                )}
                {tab === 'capture' && (
                  <CaptureScreen onPick={openCapture} onOpenMap={() => setTab('map')} />
                )}
                {tab === 'data' && (
                  <ProjectDataScreen
                    initialTarget={dataTarget}
                    onTargetConsumed={() => setDataTarget(null)}
                    onEditRecord={openEditRecord}
                    refreshKey={dataRefreshKey}
                  />
                )}
                {tab === 'more' && morePage === null && (
                  <MoreScreen
                    onOpenData={() => setTab('data')}
                    onOpenActivity={() => setMorePage('activity')}
                    onOpenPending={() => setMorePage('pending')}
                    onSwitchProject={() => setScreen('projects')}
                    onLogout={handleLogout}
                  />
                )}
                {tab === 'more' && morePage === 'activity' && (
                  <FieldActivityScreen onBack={() => setMorePage(null)} />
                )}
                {tab === 'more' && morePage === 'pending' && (
                  <UploadedDataScreen onBack={() => setMorePage(null)} />
                )}
              </View>
              <BottomNav active={tab} onChange={(next) => { setMorePage(null); setTab(next); }} />
            </View>
          )}

          <BottomSheet visible={sheet === 'manhole'} onClose={() => { setSheet(null); setEditTarget(null); }}
            title={editTarget?.item.kind === 'manhole' ? 'Update chamber' : 'Capture manhole'}>
            <ManholeScreen
              edit={editTarget?.item.kind === 'manhole'
                ? { id: editTarget.item.serverId, ...editTarget.server }
                : null}
              onSaved={finishFieldSave}
            />
          </BottomSheet>
          <BottomSheet visible={sheet === 'building'}
            onClose={() => { setSheet(null); setResumeDraft(null); setEditTarget(null); }}
            title="Update building">
            <BuildingScreen
              onSaved={finishFieldSave}
              onCancel={() => { setSheet(null); setResumeDraft(null); setEditTarget(null); }}
              resume={resumeDraft}
              edit={editTarget?.item.kind === 'building'
                ? { id: editTarget.item.serverId, ...editTarget.server }
                : null}
            />
          </BottomSheet>
          <BottomSheet visible={sheet === 'building_photo'}
            onClose={() => { setSheet(null); setEditTarget(null); }}
            title={editTarget?.item.kind === 'building_photo' ? 'Update photo observation' : 'Building photo'}>
            <BuildingPhotoScreen
              edit={editTarget?.item.kind === 'building_photo'
                ? { id: editTarget.item.serverId, ...editTarget.server }
                : null}
              onSaved={finishFieldSave}
            />
          </BottomSheet>
          <BottomSheet visible={sheet === 'street'}
            onClose={() => { setSheet(null); setEditTarget(null); }}
            title={editTarget?.item.kind === 'street' ? 'Update Road / Street' : 'Road / Street'}>
            <RoadScreen
              edit={editTarget?.item.kind === 'street'
                ? { id: editTarget.item.serverId, ...editTarget.server }
                : null}
              onSaved={finishFieldSave}
              onCancel={() => { setSheet(null); setEditTarget(null); }}
            />
          </BottomSheet>
          <BottomSheet visible={sheet === 'route'}
            onClose={() => { setSheet(null); setEditTarget(null); }}
            title={editTarget?.item.kind === 'route' ? 'Update Survey Route' : 'Track Route'}>
            <RouteCaptureScreen
              edit={editTarget?.item.kind === 'route'
                ? { id: editTarget.item.serverId, ...editTarget.server }
                : null}
              onSaved={finishFieldSave}
              onCancel={() => { setSheet(null); setEditTarget(null); }}
            />
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
