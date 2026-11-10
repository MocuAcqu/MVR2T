import type { PageId } from '@/stores/uiStore';

/** 操作後引導的步驟（規格：使用者完成一步後，提示下一步該按哪裡）。 */
export type GuideStepId = 'open-workspace' | 'extract' | 'transcribe' | 'summarize' | 'done';

export interface GuideInput {
  page: PageId;
  importStatus: string;
  extractionStatus: string;
  transcriptionStatus: string;
  summaryStatus: string;
}

/** 依目前狀態決定要提示哪一步；正在處理、失敗或取消時不提示（卡片本身已有說明）。 */
export function nextGuideStep({
  page,
  importStatus,
  extractionStatus,
  transcriptionStatus,
  summaryStatus,
}: GuideInput): GuideStepId | null {
  if (importStatus !== 'ready') return null;
  if (page === 'dashboard') return 'open-workspace';
  if (page !== 'workspace') return null;
  if (extractionStatus === 'idle') return 'extract';
  if (extractionStatus !== 'completed') return null;
  if (transcriptionStatus === 'idle') return 'transcribe';
  if (transcriptionStatus !== 'completed') return null;
  if (summaryStatus === 'idle') return 'summarize';
  if (summaryStatus === 'completed') return 'done';
  return null;
}

export const GUIDE_MESSAGES: Record<GuideStepId, { title: string; body: string }> = {
  'open-workspace': { title: '檔案準備好了！', body: '按「開啟工作區」，接下來的處理都在那裡進行。' },
  extract: { title: '檔案匯入好了！', body: '下一步按「抽取音訊」，我會把聲音整理好、在停頓處切成小段。' },
  transcribe: {
    title: '聲音切好了！',
    body: '選擇錄音的語言（不確定就用「自動偵測」），再按「開始語音辨識」。第一次需要 1～2 分鐘載入模型。',
  },
  summarize: {
    title: '逐字稿完成了！',
    body: '勾選想要的摘要內容，再按「產生摘要」。第一次需要約 1 分鐘載入摘要模型，長錄音會分段整理，需要多一點時間。',
  },
  done: { title: '摘要完成了！', body: '點項目旁的時間，可以跳到逐字稿中對應的句子。心智圖會在之後的版本加入。' },
};
