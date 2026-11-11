/// <reference types="vite/client" />

interface ImportMetaEnv {
  /** Browser-facing API base path or absolute URL. */
  readonly VITE_API_URL?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
