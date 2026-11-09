import type { ReactNode } from 'react';
import { cn } from '@/lib/utils';
import type { GuideStepId } from './guide';
import { useActiveGuideStep } from './useGuide';

/** 包住「下一步」的按鈕：輪到它時外圈發光，旁邊出現輕推的箭頭。 */
export function GuideTarget({ step, children }: { step: GuideStepId; children: ReactNode }) {
  const active = useActiveGuideStep() === step;
  return (
    <span className="inline-flex items-center gap-3">
      <span className={cn('inline-flex rounded-pill', active && 'guide-glow')}>{children}</span>
      {active ? (
        <span aria-hidden className="guide-nudge select-none text-xl leading-none">
          ◀
        </span>
      ) : null}
    </span>
  );
}
