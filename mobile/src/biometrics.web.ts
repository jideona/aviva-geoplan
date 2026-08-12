// Web counterpart to biometrics.ts. expo-local-authentication wraps the
// native iOS/Android biometric APIs and has no browser implementation — the
// closest browser equivalent is WebAuthn, which needs a server-side relying
// party (challenge issuance + credential verification) this API doesn't have.
// Rather than show a button that can't do anything in a browser, every
// function here reports "unavailable" so callers (LockScreen trigger in
// App.tsx, the Dashboard menu toggle) hide the feature entirely on web.
const LOCK_KEY = 'bio_lock_enabled';

export async function hasBiometricHardware(): Promise<boolean> {
  return false;
}

export async function supportedTypeLabel(): Promise<string> {
  return 'Device biometrics';
}

export async function isBiometricLockEnabled(): Promise<boolean> {
  try { return window.localStorage.getItem(LOCK_KEY) === '1'; } catch { return false; }
}

export async function setBiometricLockEnabled(v: boolean): Promise<void> {
  try {
    if (v) window.localStorage.setItem(LOCK_KEY, '1');
    else window.localStorage.removeItem(LOCK_KEY);
  } catch {}
}

export async function authenticateBiometric(_reason: string): Promise<boolean> {
  return false;
}
