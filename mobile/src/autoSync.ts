// Auto-uploads the outbox as soon as a connection is available, so a
// surveyor doesn't have to remember to tap "Sync now" after coming back
// online. Runs once at the app root (App.tsx) rather than on any one
// screen, so it keeps working no matter which screen is showing, and goes
// through sync.ts's runSync() — the same dedupe guard the manual "Sync
// now" / "Upload pending" buttons use — so an auto-triggered sync can never
// race a manual one.
import { useEffect, useRef } from 'react';
import NetInfo from '@react-native-community/netinfo';
import { kvGet, pendingCount } from './db';
import { runSync } from './sync';
import { notify } from './notify';

// While online, also retry on this cadence — catches anything a
// connectivity-transition event missed (some platforms are flaky about
// firing it), and anything whose first attempt raced a connection that
// wasn't fully up yet. Deliberately simple (flat interval, no backoff) —
// pendingCount() short-circuits every tick that has nothing to do, so an
// unreachable server just means quiet no-op ticks, not a hammering retry.
const RETRY_INTERVAL_MS = 60_000;

export function useAutoSync(enabled: boolean) {
  const wasOnline = useRef(false);

  useEffect(() => {
    if (!enabled) return;

    async function attempt() {
      const pid = await kvGet('projectId');
      if (!pid) return; // no project picked yet — nothing to sync
      if ((await pendingCount()) === 0) return;
      try {
        const r = await runSync(pid);
        if (r.done > 0) {
          notify('Synced', `Back online — sent ${r.done} update${r.done === 1 ? '' : 's'} automatically.`);
        }
      } catch { /* best-effort — the next transition or interval tick tries again */ }
    }

    const unsub = NetInfo.addEventListener((state) => {
      const online = !!state.isConnected;
      if (online && !wasOnline.current) void attempt(); // offline -> online edge
      wasOnline.current = online;
    });

    // Covers the app launching (or this becoming enabled, e.g. right after
    // login) already online with pending work left over from an earlier
    // offline session — the listener above only fires on a transition, so
    // "already connected" at mount would otherwise never trigger a sync.
    NetInfo.fetch().then((state) => {
      wasOnline.current = !!state.isConnected;
      if (wasOnline.current) void attempt();
    });

    const interval = setInterval(() => { if (wasOnline.current) void attempt(); }, RETRY_INTERVAL_MS);

    return () => { unsub(); clearInterval(interval); };
  }, [enabled]);
}
