import { t } from '@/i18n';
/** 處理中顯示：說明睡眠對處理的影響（Electron 會請系統不要因閒置而睡眠，見 electron/main.ts setKeepAwake）。 */
export function KeepAwakeNote() {
  return (
    <p className="text-xs text-body-gray">
      {t('處理中 MVR2T 會請電腦不要自動睡眠，螢幕可以照常關閉。若電腦仍進入睡眠（例如闔上筆電），處理會暫停，喚醒後會自動繼續。')}
    </p>
  );
}
