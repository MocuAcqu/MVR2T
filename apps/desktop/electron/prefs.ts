/**
 * 使用者偏好（Main 端，userData/preferences.json）。只存設定值（例如匯出資料夾的路徑），
 * 不存任何媒體、逐字稿、摘要內容（PROJECT_SPEC §8.3 Session-based）。不 import electron，方便測試。
 */
import { readFile, stat, writeFile, rename } from 'node:fs/promises';
import path from 'node:path';

export interface Prefs {
  lastExportFolder: string | null;
  fixedExportFolder: string | null;
}

const EMPTY: Prefs = { lastExportFolder: null, fixedExportFolder: null };

const validPath = (v: unknown): string | null => (typeof v === 'string' && v.length > 0 && v.length < 1024 && path.isAbsolute(v) ? v : null);

/** 讀取偏好；檔案不存在或損壞時回傳預設值（不丟錯）。 */
export async function loadPrefs(file: string): Promise<Prefs> {
  try {
    const raw = JSON.parse(await readFile(file, 'utf8')) as Record<string, unknown>;
    return { lastExportFolder: validPath(raw.lastExportFolder), fixedExportFolder: validPath(raw.fixedExportFolder) };
  } catch {
    return { ...EMPTY };
  }
}

/** 合併後寫入（先寫暫存檔再改名，避免寫到一半）。 */
export async function savePrefs(file: string, patch: Partial<Prefs>): Promise<Prefs> {
  const next = { ...(await loadPrefs(file)), ...patch };
  const tmp = `${file}.tmp`;
  await writeFile(tmp, JSON.stringify(next, null, 2), 'utf8');
  await rename(tmp, file);
  return next;
}

export async function isDirectory(p: string | null): Promise<boolean> {
  if (!p) return false;
  try {
    return (await stat(p)).isDirectory();
  } catch {
    return false;
  }
}
