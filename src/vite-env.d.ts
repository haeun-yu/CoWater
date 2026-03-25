/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_MOTH_SUB_URL?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
