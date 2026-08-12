// Bundled as a rasterized PNG rather than the source SVG — Metro's default
// asset pipeline (used everywhere else in this project for icons/splash)
// handles PNG on both native and web with zero extra config; SVG would need
// react-native-svg (native) or Metro's svg transformer, neither of which is
// wired up here, and this sandbox can't reliably `npm install` a new native
// dependency into the mounted project (see project memory). Source SVG kept
// alongside at assets/aviva-logo.svg for future re-export if ever needed.
import { Image, type ImageStyle, type StyleProp } from 'react-native';

export default function AvivaLogo({ style }: { style?: StyleProp<ImageStyle> }) {
  return (
    <Image
      source={require('../../assets/aviva-logo.png')}
      resizeMode="contain"
      style={style}
      accessibilityLabel="Aviva Networx"
    />
  );
}
