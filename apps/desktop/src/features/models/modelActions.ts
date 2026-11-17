import type { ModelManagerState, PackageId } from '@shared/types/api';
import {
  deleteModelPackage,
  deleteUnusedModel,
  downloadAllModels,
  getBackendConnection,
  getModels,
  modelAction,
} from '@/services/api';
import { t } from '@/i18n';

/** 模型管理的動作。回傳最新狀態；錯誤時丟出（訊息是給使用者看的繁體中文）。 */
async function conn() {
  const c = await getBackendConnection();
  if (!c) throw new Error(t('本機後端尚未連線。'));
  return c;
}

export const packageAction = async (pkg: PackageId, action: 'download' | 'verify' | 'cancel'): Promise<ModelManagerState> =>
  modelAction(await conn(), pkg, action);

export const downloadAll = async (): Promise<ModelManagerState> => downloadAllModels(await conn());

export async function deletePackage(pkg: PackageId): Promise<ModelManagerState> {
  const c = await conn();
  await deleteModelPackage(c, pkg);
  return getModels(c);
}

export async function deleteUnused(key: string): Promise<ModelManagerState> {
  const c = await conn();
  await deleteUnusedModel(c, key);
  return getModels(c);
}

/** 下載剩餘時間（秒）；速度未知時 null */
export function etaSeconds(done: number, total: number, speed: number): number | null {
  if (speed <= 0 || total <= done) return null;
  return (total - done) / speed;
}

/** 「約剩 3 分鐘」 */
export function formatEta(seconds: number | null): string {
  if (seconds === null || !Number.isFinite(seconds)) return '';
  if (seconds < 60) return t('不到 1 分鐘');
  if (seconds < 3600) return t('約剩 {0} 分鐘', Math.ceil(seconds / 60));
  const h = Math.floor(seconds / 3600);
  const m = Math.ceil((seconds % 3600) / 60);
  return t('約剩 {0} 小時{1}', h, m ? t(' {0} 分鐘', m) : '');
}

export const shortRevision = (rev: string) => rev.slice(0, 7);
