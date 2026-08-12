// Web counterpart to notify.ts — see that file for why this exists.
// window.alert() is blunt but always visible, which is the actual
// requirement here (surfacing errors that were previously silent).
export function notify(title: string, message?: string) {
  try {
    window.alert(message ? `${title}\n\n${message}` : title);
  } catch {
    // eslint-disable-next-line no-console
    console.warn(`[${title}]`, message);
  }
}
