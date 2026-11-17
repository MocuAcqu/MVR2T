import { Mono } from '@/components/mono/Mono';
import { cn } from '@/lib/utils';
import { GUIDE_MESSAGES, type GuideStepId } from './guide';
import { t } from '@/i18n';
import { useActiveGuideStep } from './useGuide';

/** Mono 的對話框（外觀）。設計規範頁也用它展示。 */
export function GuideBubble({ step, className }: { step: GuideStepId; className?: string }) {
  const msg = GUIDE_MESSAGES[step];
  return (
    <div className={cn('flex items-end gap-3', className)} role="status" aria-live="polite">
      <Mono animation={step === 'done' ? 'done' : 'hint'} scale={2} />
      <div className="relative mb-2 min-w-0 flex-1 border-[3px] border-foreground bg-background px-4 py-3 text-sm shadow-[4px_4px_0_0_#000]">
        <span
          aria-hidden
          className="absolute -left-[12px] bottom-3 size-0 border-y-[6px] border-r-[9px] border-y-transparent border-r-foreground"
        />
        <p className="font-bold">{t(msg.title)}</p>
        <p className="mt-1 text-body-gray">{t(msg.body)}</p>
      </div>
    </div>
  );
}

/** 輪到 `step` 時出現；要關閉請到「設定 → 操作引導」。 */
export function GuideCoach({ step, className }: { step: GuideStepId; className?: string }) {
  const active = useActiveGuideStep() === step;
  if (!active) return null;
  return <GuideBubble step={step} className={className} />;
}
