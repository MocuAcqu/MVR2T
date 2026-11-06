/// <reference types="vite/client" />

interface ImportMetaEnv {
  /** 純瀏覽器開發（不經 Electron）時覆寫後端位址。 */
  readonly VITE_BACKEND_URL?: string;
}
