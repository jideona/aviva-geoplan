/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_API_URL?: string
  readonly VITE_BASEMAP_STYLE_URL?: string
}
interface ImportMeta { readonly env: ImportMetaEnv }
