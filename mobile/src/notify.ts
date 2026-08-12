// Cross-platform alert. react-native-web's Alert.alert is a no-op on web (it
// just console.warns — confirmed by hitting a real error in the browser and
// seeing nothing happen), so every error path across the app that used
// Alert.alert() directly was silently swallowed on the PWA build. Native
// keeps using the real Alert; web falls through to notify.web.ts.
import { Alert } from 'react-native';

export function notify(title: string, message?: string) {
  Alert.alert(title, message);
}
