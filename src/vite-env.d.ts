/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_DEV_TOKEN?: string;
  readonly VITE_API_BASE?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
