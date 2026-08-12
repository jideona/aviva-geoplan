// Web counterpart to confirm.ts — Alert.alert's buttons are a no-op on
// react-native-web, so this uses the browser's native confirm() instead.
export function confirmAction(title: string, message: string): Promise<boolean> {
  return Promise.resolve(window.confirm(`${title}\n\n${message}`));
}
