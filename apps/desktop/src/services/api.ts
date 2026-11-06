/**
 * Backend API client。
 * 之後所有後端呼叫（模型、媒體、ASR…）都集中在 services/，元件不直接 fetch。
 *
 * Phase 03：在 Electron 內，後端位址（動態連接埠）與一次性連線憑證都由 Main Process 提供；
 * 每個請求都帶 `Authorization: Bearer <token>`。
 * 在一般瀏覽器預覽時（沒有 window.mvr2t），改連手動啟動的開發用後端，不帶憑證。
 */
import { DEFAULT_BACKEND_URL } from '@shared/constants/app';
import type { HealthResponse } from '@shared/types/api';
import type { AppInfo } from '@shared/types/ipc';

export interface BackendConnection {
  url: string;
  token: string | null;
}

/** 是否在 Electron 視窗內（preload 有注入橋接）。 */
export function isElectron(): boolean {
  return typeof window !== 'undefined' && !!window.mvr2t;
}

/** 取得 Electron 提供的應用程式資訊；不在 Electron 內時回傳 null。 */
export async function getAppInfo(): Promise<AppInfo | null> {
  if (!window.mvr2t) return null;
  try {
    return await window.mvr2t.getAppInfo();
  } catch {
    return null;
  }
}

/** 瀏覽器預覽用的後端位址：VITE_BACKEND_URL，其次預設 127.0.0.1:8765。 */
export function browserFallbackConnection(): BackendConnection {
  return { url: import.meta.env.VITE_BACKEND_URL ?? DEFAULT_BACKEND_URL, token: null };
}

/** 取得目前可用的後端連線；Electron 內後端尚未就緒時回傳 null。 */
export async function getBackendConnection(): Promise<BackendConnection | null> {
  if (!window.mvr2t) return browserFallbackConnection();
  const state = await window.mvr2t.getBackendState();
  return state.phase === 'running' && state.url ? { url: state.url, token: state.token } : null;
}

/** 所有後端請求的共同入口：自動加上憑證標頭。 */
export async function backendFetch(conn: BackendConnection, path: string, init: RequestInit = {}): Promise<Response> {
  const headers = new Headers(init.headers);
  if (conn.token) headers.set('Authorization', `Bearer ${conn.token}`);
  return fetch(`${conn.url}${path}`, { ...init, headers });
}

export async function fetchHealth(conn: BackendConnection, signal?: AbortSignal): Promise<HealthResponse> {
  const res = await backendFetch(conn, '/api/health', { signal });
  if (!res.ok) throw new Error(`Backend responded with HTTP ${res.status}`);
  return (await res.json()) as HealthResponse;
}
