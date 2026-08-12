// Native confirm dialog, wrapped as a Promise<boolean> so call sites don't
// need to know about RN's callback-style Alert buttons. Mirrors notify.ts's
// native/.web split (Alert.alert has the same real-vs-web-noop gap as
// notify's usage did).
import { Alert } from 'react-native';

export function confirmAction(title: string, message: string): Promise<boolean> {
  return new Promise((resolve) => {
    Alert.alert(title, message, [
      { text: 'Cancel', style: 'cancel', onPress: () => resolve(false) },
      { text: 'Delete', style: 'destructive', onPress: () => resolve(true) },
    ]);
  });
}
