// Face ID / Touch ID / fingerprint app-lock. This does NOT cache the user's
// password or use biometrics to log in — the refresh token issued at login
// already persists in the keychain (see auth.ts) and keeps the surveyor
// signed in across app restarts with no prompt at all. That's the actual gap:
// a device left unlocked (or just backgrounded) gives anyone holding it full
// access to an already-authenticated session. Biometrics here gate *that*
// session behind a hardware-backed prompt; App.tsx shows LockScreen instead
// of the real content whenever the lock is enabled, at boot and whenever the
// app returns from the background.
import * as LocalAuthentication from 'expo-local-authentication';
import * as SecureStore from 'expo-secure-store';

const LOCK_KEY = 'bio_lock_enabled';

export async function hasBiometricHardware(): Promise<boolean> {
  try {
    const hw = await LocalAuthentication.hasHardwareAsync();
    if (!hw) return false;
    return await LocalAuthentication.isEnrolledAsync();
  } catch {
    return false;
  }
}

// Human label for whatever the device actually has enrolled, for button/copy text.
export async function supportedTypeLabel(): Promise<string> {
  try {
    const types = await LocalAuthentication.supportedAuthenticationTypesAsync();
    if (types.includes(LocalAuthentication.AuthenticationType.FACIAL_RECOGNITION)) return 'Face ID';
    if (types.includes(LocalAuthentication.AuthenticationType.FINGERPRINT)) return 'Touch ID';
    if (types.includes(LocalAuthentication.AuthenticationType.IRIS)) return 'Iris unlock';
    return 'Device biometrics';
  } catch {
    return 'Device biometrics';
  }
}

export async function isBiometricLockEnabled(): Promise<boolean> {
  return (await SecureStore.getItemAsync(LOCK_KEY)) === '1';
}

export async function setBiometricLockEnabled(v: boolean): Promise<void> {
  if (v) await SecureStore.setItemAsync(LOCK_KEY, '1');
  else await SecureStore.deleteItemAsync(LOCK_KEY);
}

// Prompts and returns whether the OS confirmed the user's identity. Falls
// back to the device passcode automatically (disableDeviceFallback: false)
// so a surveyor who, say, cut a finger isn't locked out of their own phone.
export async function authenticateBiometric(reason: string): Promise<boolean> {
  try {
    const res = await LocalAuthentication.authenticateAsync({
      promptMessage: reason,
      cancelLabel: 'Use password instead',
      disableDeviceFallback: false,
    });
    return res.success;
  } catch {
    return false;
  }
}
