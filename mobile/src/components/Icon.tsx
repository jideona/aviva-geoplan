// Aviva Networx Design System v1.0 — icon set.
// Replaces ad-hoc Unicode glyphs (⌂ ▢ △ ⇆ ◉ ▣ ↺ ⇧ …) used as icons in
// DashboardScreen/Fab, which render inconsistently across platforms/fonts
// and were the root cause of the map-pin glyph crash fixed in
// 778b29b. One SVG-based component, one registry of names, used everywhere
// an icon is needed (nav tabs, quick actions, KPI tiles, More-menu rows).
//
// Style: 24x24 grid, stroke-based outline icons (round caps/joins), so a
// single `color` prop re-tints an icon for active/inactive nav state,
// status colour (STATUS.flagged), etc. — matching how COLOR tokens are
// used everywhere else in this design system (Vol.2 §01).
import Svg, { Circle, Line, Path, Rect } from 'react-native-svg';

export type IconName =
  | 'home' | 'map' | 'capture' | 'data' | 'more'
  | 'building' | 'manhole' | 'road' | 'route' | 'photo'
  | 'flagged' | 'synced' | 'resumeDraft' | 'uploadedData'
  | 'back' | 'chevronRight' | 'search' | 'filter' | 'close'
  | 'edit' | 'check' | 'users' | 'settings' | 'signOut'
  | 'fieldActivity' | 'pendingDrafts' | 'qaReview' | 'project'
  | 'switchProject' | 'layerBuildings' | 'layerNetwork' | 'layerSatellite'
  | 'zoomIn' | 'zoomOut' | 'locate' | 'delete' | 'play';

export function Icon({ name, size = 20, color = '#1A1A1A', style }: {
  name: IconName; size?: number; color?: string; style?: any;
}) {
  const p = {
    stroke: color, strokeWidth: 1.75,
    strokeLinecap: 'round' as const, strokeLinejoin: 'round' as const,
    fill: 'none' as const,
  };
  return (
    <Svg width={size} height={size} viewBox="0 0 24 24" style={style}>
      {renderGlyph(name, p, color)}
    </Svg>
  );
}

function renderGlyph(
  name: IconName,
  p: { stroke: string; strokeWidth: number; strokeLinecap: 'round'; strokeLinejoin: 'round'; fill: 'none' },
  color: string,
) {
  switch (name) {
    case 'home':
      return (<>
        <Path d="M4 11.5 12 4l8 7.5" {...p} />
        <Path d="M6 10.5V20h5v-5h2v5h5v-9.5" {...p} />
      </>);
    case 'map':
      return (<>
        <Path d="M4 6 9 4l6 2 5-2v14l-5 2-6-2-5 2Z" {...p} />
        <Line x1={9} y1={4} x2={9} y2={18} {...p} />
        <Line x1={15} y1={6} x2={15} y2={20} {...p} />
      </>);
    case 'capture':
      return (<>
        <Line x1={12} y1={5} x2={12} y2={19} {...p} />
        <Line x1={5} y1={12} x2={19} y2={12} {...p} />
      </>);
    case 'data':
      return (<>
        <Line x1={4} y1={7} x2={20} y2={7} {...p} />
        <Line x1={4} y1={12} x2={20} y2={12} {...p} />
        <Line x1={4} y1={17} x2={14} y2={17} {...p} />
      </>);
    case 'more':
      return (<>
        <Circle cx={6} cy={12} r={1.4} fill={color} stroke="none" />
        <Circle cx={12} cy={12} r={1.4} fill={color} stroke="none" />
        <Circle cx={18} cy={12} r={1.4} fill={color} stroke="none" />
      </>);
    case 'building':
      return (<>
        <Rect x={6} y={4} width={12} height={16} {...p} />
        <Rect x={8.25} y={7} width={2} height={2} fill={color} stroke="none" />
        <Rect x={13.75} y={7} width={2} height={2} fill={color} stroke="none" />
        <Rect x={8.25} y={11} width={2} height={2} fill={color} stroke="none" />
        <Rect x={13.75} y={11} width={2} height={2} fill={color} stroke="none" />
        <Rect x={10} y={15.5} width={4} height={4.5} {...p} />
      </>);
    case 'manhole':
      return (<>
        <Circle cx={12} cy={12} r={8} {...p} />
        <Circle cx={12} cy={12} r={3} {...p} />
        <Line x1={12} y1={4} x2={12} y2={9} {...p} />
        <Line x1={12} y1={15} x2={12} y2={20} {...p} />
        <Line x1={4} y1={12} x2={9} y2={12} {...p} />
        <Line x1={15} y1={12} x2={20} y2={12} {...p} />
      </>);
    case 'road':
      return (<>
        <Path d="M9.5 20 11 4" {...p} />
        <Path d="M14.5 20 13 4" {...p} />
        <Line x1={12} y1={20} x2={12} y2={4} stroke={color} strokeWidth={1.75} strokeLinecap="round" strokeDasharray="2.2,3.4" />
      </>);
    case 'route':
      return (<>
        <Path d="M4 18 9 10 14 14 20 6" stroke={color} strokeWidth={1.75} strokeLinecap="round" strokeLinejoin="round" fill="none" strokeDasharray="3,3" />
        <Circle cx={4} cy={18} r={1.6} fill={color} stroke="none" />
        <Circle cx={20} cy={6} r={1.6} fill={color} stroke="none" />
      </>);
    case 'photo':
      return (<>
        <Path d="M8 7 9.3 4.6h5.4L16 7" {...p} />
        <Rect x={3} y={7} width={18} height={13} rx={2} {...p} />
        <Circle cx={12} cy={13.5} r={3.4} {...p} />
      </>);
    case 'flagged':
      return (<>
        <Path d="M12 4 21 20H3Z" {...p} />
        <Line x1={12} y1={10} x2={12} y2={14} {...p} />
        <Circle cx={12} cy={17} r={0.9} fill={color} stroke="none" />
      </>);
    case 'synced':
      return (<>
        <Path d="M20 12a8 8 0 1 1-2.34-5.66" {...p} />
        <Path d="M20 4v5h-5" {...p} />
      </>);
    case 'resumeDraft':
      return (<>
        <Path d="M4 11h9a5 5 0 0 1 0 10h-2" {...p} />
        <Path d="M8 6 4 11l4 5" {...p} />
      </>);
    case 'uploadedData':
      return (<>
        <Line x1={12} y1={4} x2={12} y2={14} {...p} />
        <Path d="M8 8 12 4l4 4" {...p} />
        <Path d="M4 16v3a1 1 0 0 0 1 1h14a1 1 0 0 0 1-1v-3" {...p} />
      </>);
    case 'back':
      return <Path d="M15 5 8 12l7 7" {...p} />;
    case 'chevronRight':
      return <Path d="M9 5l7 7-7 7" {...p} />;
    case 'search':
      return (<>
        <Circle cx={10.5} cy={10.5} r={6.5} {...p} />
        <Line x1={15.3} y1={15.3} x2={20} y2={20} {...p} />
      </>);
    case 'filter':
      return (<>
        <Line x1={4} y1={7} x2={20} y2={7} {...p} />
        <Line x1={4} y1={12} x2={20} y2={12} {...p} />
        <Line x1={4} y1={17} x2={20} y2={17} {...p} />
        <Circle cx={8} cy={7} r={2} fill={color} stroke="none" />
        <Circle cx={16} cy={12} r={2} fill={color} stroke="none" />
        <Circle cx={11} cy={17} r={2} fill={color} stroke="none" />
      </>);
    case 'close':
      return (<>
        <Line x1={6} y1={6} x2={18} y2={18} {...p} />
        <Line x1={18} y1={6} x2={6} y2={18} {...p} />
      </>);
    case 'edit':
      return (<>
        <Path d="M4 20 5 15.5 15 5.5l3.5 3.5L8.5 19Z" {...p} />
        <Line x1={13} y1={7.5} x2={16.5} y2={11} {...p} />
      </>);
    case 'check':
      return <Path d="M4 12.5 9.5 18 20 6" {...p} />;
    case 'users':
      return (<>
        <Circle cx={9} cy={8} r={3} {...p} />
        <Path d="M3.5 20v-1.5a5.5 5.5 0 0 1 11 0V20" {...p} />
        <Circle cx={17.5} cy={9} r={2.5} {...p} />
        <Path d="M15.5 20v-1a4.5 4.5 0 0 1 6-4.24" {...p} />
      </>);
    case 'settings':
      return (<>
        <Circle cx={12} cy={12} r={3} {...p} />
        <Line x1={18} y1={12} x2={20.5} y2={12} {...p} />
        <Line x1={15} y1={17.2} x2={16.3} y2={19.4} {...p} />
        <Line x1={9} y1={17.2} x2={7.8} y2={19.4} {...p} />
        <Line x1={6} y1={12} x2={3.5} y2={12} {...p} />
        <Line x1={9} y1={6.8} x2={7.8} y2={4.6} {...p} />
        <Line x1={15} y1={6.8} x2={16.3} y2={4.6} {...p} />
      </>);
    case 'signOut':
      return (<>
        <Path d="M13 4H6a1 1 0 0 0-1 1v14a1 1 0 0 0 1 1h7" {...p} />
        <Line x1={10} y1={12} x2={21} y2={12} {...p} />
        <Path d="M17 8 21 12l-4 4" {...p} />
      </>);
    case 'fieldActivity':
      return (<>
        <Circle cx={12} cy={12} r={8} {...p} />
        <Line x1={12} y1={12} x2={12} y2={7} {...p} />
        <Line x1={12} y1={12} x2={16} y2={13} {...p} />
      </>);
    case 'pendingDrafts':
      return (<>
        <Path d="M7 3h7l4 4v13a1 1 0 0 1-1 1H7a1 1 0 0 1-1-1V4a1 1 0 0 1 1-1Z" {...p} />
        <Path d="M14 3v4h4" {...p} />
        <Circle cx={16.5} cy={16.5} r={3.3} {...p} />
        <Line x1={16.5} y1={15} x2={16.5} y2={16.5} {...p} />
        <Line x1={16.5} y1={16.5} x2={17.7} y2={17.2} {...p} />
      </>);
    case 'qaReview':
      return (<>
        <Path d="M12 3 19 6v5c0 5-3 8.5-7 10-4-1.5-7-5-7-10V6Z" {...p} />
        <Path d="M8.5 12 11 14.5 16 9" {...p} />
      </>);
    case 'project':
      return <Path d="M3 7a1 1 0 0 1 1-1h5l2 2h9a1 1 0 0 1 1 1v9a1 1 0 0 1-1 1H4a1 1 0 0 1-1-1Z" {...p} />;
    case 'switchProject':
      return (<>
        <Path d="M4 8h13" {...p} />
        <Path d="M14 4l3 4-3 4" {...p} />
        <Path d="M20 16H7" {...p} />
        <Path d="M10 12l-3 4 3 4" {...p} />
      </>);
    case 'layerBuildings':
      return (<>
        <Rect x={6} y={4} width={12} height={16} {...p} />
        <Rect x={8.25} y={7} width={2} height={2} fill={color} stroke="none" />
        <Rect x={13.75} y={7} width={2} height={2} fill={color} stroke="none" />
        <Rect x={8.25} y={11} width={2} height={2} fill={color} stroke="none" />
        <Rect x={13.75} y={11} width={2} height={2} fill={color} stroke="none" />
      </>);
    case 'layerNetwork':
      return (<>
        <Circle cx={6} cy={7} r={2} {...p} />
        <Circle cx={18} cy={7} r={2} {...p} />
        <Circle cx={12} cy={17} r={2} {...p} />
        <Line x1={8} y1={8} x2={16} y2={8} {...p} />
        <Line x1={7} y1={9} x2={11} y2={15} {...p} />
        <Line x1={17} y1={9} x2={13} y2={15} {...p} />
      </>);
    case 'layerSatellite':
      return (<>
        <Circle cx={12} cy={12} r={5} {...p} />
        <Circle cx={12} cy={12} r={9} stroke={color} strokeWidth={1.75} fill="none" strokeDasharray="2,3" />
      </>);
    case 'zoomIn':
      return (<>
        <Circle cx={12} cy={12} r={8} {...p} />
        <Line x1={12} y1={8} x2={12} y2={16} {...p} />
        <Line x1={8} y1={12} x2={16} y2={12} {...p} />
      </>);
    case 'zoomOut':
      return (<>
        <Circle cx={12} cy={12} r={8} {...p} />
        <Line x1={8} y1={12} x2={16} y2={12} {...p} />
      </>);
    case 'locate':
      return (<>
        <Circle cx={12} cy={12} r={3} fill={color} stroke="none" />
        <Circle cx={12} cy={12} r={7} {...p} />
        <Line x1={12} y1={2} x2={12} y2={5} {...p} />
        <Line x1={12} y1={19} x2={12} y2={22} {...p} />
        <Line x1={2} y1={12} x2={5} y2={12} {...p} />
        <Line x1={19} y1={12} x2={22} y2={12} {...p} />
      </>);
    case 'delete':
      return (<>
        <Rect x={6} y={8} width={12} height={12} rx={1} {...p} />
        <Line x1={4} y1={8} x2={20} y2={8} {...p} />
        <Path d="M9 8V6a1 1 0 0 1 1-1h4a1 1 0 0 1 1 1v2" {...p} />
        <Line x1={10} y1={11} x2={10} y2={17} {...p} />
        <Line x1={14} y1={11} x2={14} y2={17} {...p} />
      </>);
    case 'play':
      return <Path d="M8 5.5 18 12 8 18.5Z" fill={color} stroke="none" />;
    default:
      return <Circle cx={12} cy={12} r={8} {...p} />;
  }
}
