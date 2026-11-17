/**
 * Main 行程的英文介面（對話框標題、後端狀態訊息、匯出錯誤）。renderer 讀取／設定介面偏好時同步語言。
 * 原文（繁體中文）就是 key，{0}、{1}… 代入參數；查不到就顯示原文。
 */
export type MainLang = 'zh-TW' | 'en';
let lang: MainLang = 'zh-TW';

export function setMainLang(value: MainLang): void {
  lang = value;
}

export const MAIN_EN: Record<string, string> = {
  另存新檔: 'Save as',
  選擇固定的匯出資料夾: 'Choose a fixed export folder',
  使用這個資料夾: 'Use this folder',
  選擇匯出資料夾: 'Choose the export folder',
  匯出到這裡: 'Export here',
  '後端尚未就緒，請稍後再試。': 'The backend is not ready yet. Please try again shortly.',
  'PNG 圖片': 'PNG image',
  'SVG 向量圖': 'SVG vector image',
  同名檔案太多: 'Too many files with the same name',
  '無法寫入檔案，可能被防毒軟體（例如勒索軟體防護）阻擋，或資料夾沒有寫入權限。請在防毒軟體中允許 MVR2T，再按「重新匯出失敗的項目」。':
    'Cannot write the file. It may be blocked by antivirus software (for example ransomware protection), or the folder is not writable. Allow MVR2T in the antivirus software, then click “Retry failed exports”.',
  '檔案正被其他程式使用，請關閉後再按「重新匯出失敗的項目」。': 'The file is in use by another program. Close it, then click “Retry failed exports”.',
  '磁碟空間不足。': 'Not enough disk space.',
  '後端回應 {0}': 'The backend responded {0}',
  '還沒有心智圖。': 'There is no mind map yet.',
  '安裝檔缺少後端程式：{0}。請重新安裝 MVR2T。': 'The backend program is missing from the installation: {0}. Please reinstall MVR2T.',
  '找不到後端的 Python：{0}。請依 README 在 apps/backend 建立 .venv（Python 3.11）並安裝 requirements/dev.txt。':
    'The backend Python was not found: {0}. Create apps/backend/.venv (Python 3.11) and install requirements/dev.txt as described in the README.',
  '無法啟動後端：{0}': 'Cannot start the backend: {0}',
  '後端在 {0} 秒內沒有就緒。': 'The backend was not ready within {0} seconds.',
  '後端意外結束（{0}）。': 'The backend stopped unexpectedly ({0}).',
  '訊號 {0}': 'signal {0}',
  '代碼 {0}': 'code {0}',
  未知: 'unknown',
};

export function mt(zh: string, ...args: (string | number | null | undefined)[]): string {
  const s = lang === 'en' ? (MAIN_EN[zh] ?? zh) : zh;
  return args.length ? s.replace(/\{(\d+)\}/g, (_m, i: string) => String(args[Number(i)] ?? '')) : s;
}
