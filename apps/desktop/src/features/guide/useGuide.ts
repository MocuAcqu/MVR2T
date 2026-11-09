import { useSessionStore } from '@/stores/sessionStore';
import { useUiStore } from '@/stores/uiStore';
import { nextGuideStep, type GuideStepId } from './guide';
import { useGuideStore } from './guideStore';

/** 目前要顯示的引導步驟（引導在設定頁關閉時為 null）。 */
export function useActiveGuideStep(): GuideStepId | null {
  const page = useUiStore((s) => s.page);
  const importStatus = useSessionStore((s) => s.import.status);
  const extractionStatus = useSessionStore((s) => s.extraction.status);
  const transcriptionStatus = useSessionStore((s) => s.transcription.status);
  const enabled = useGuideStore((s) => s.enabled);
  if (!enabled) return null;
  return nextGuideStep({ page, importStatus, extractionStatus, transcriptionStatus });
}
