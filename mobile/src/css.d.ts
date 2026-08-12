// Metro handles CSS imports (used for maplibre-gl's stylesheet) at bundle
// time on web; this just tells tsc the import is legal so typecheck doesn't
// choke on a side-effect-only import with no JS types.
declare module '*.css';
