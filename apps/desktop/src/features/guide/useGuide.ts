import { useSessionStore } from '@/stores/sessionStore';
import { useUiStore } from '@/stores/uiStore';
import { nextGuideStep, type GuideStepId } from './guide';
import { useGuideStore } from './guideStore';

/** 目前要顯示的引導步驟（已關閉引導、或這一步已按「知道了」時為 null）。 */
export function useActiveGuideStep(): GuideStepId | null {
  const page = useUiStore((s) => s.page);
  const importStatus = useSessionStore((s) => s.import.status);
  const extractionStatus = useSessionStore((s) => s.extraction.status);
  const transcriptionStatus = useSessionStore((s) => s.transcription.status);
  const enabled = useGuideStore((s) => s.enabled);
  const dismissed = useGuideStore((s) => s.dismissed);
  if (!enabled) return null;
  const step = nextGuideStep({ page, importStatus, extractionStatus, transcriptionStatus });
  return step && !dismissed.includes(step) ? step : null;
}
