import { Mono } from '@/components/mono/Mono';
import { cn } from '@/lib/utils';
import { GUIDE_MESSAGES, type GuideStepId } from './guide';
import { useGuideStore } from './guideStore';
import { useActiveGuideStep } from './useGuide';

/** Mono 的對話框（外觀）。設計規範頁也用它展示。 */
export function GuideBubble({
  step,
  onDismiss,
  onDisable,
  className,
}: {
  step: GuideStepId;
  onDismiss: () => void;
  onDisable: () => void;
  className?: string;
}) {
  const msg = GUIDE_MESSAGES[step];
  return (
    <div className={cn('flex items-end gap-3', className)} role="status" aria-live="polite">
      <Mono animation={step === 'done' ? 'done' : 'hint'} scale={2} />
      <div className="relative mb-2 min-w-0 flex-1 border-[3px] border-foreground bg-background px-4 py-3 text-sm shadow-[4px_4px_0_0_#000]">
        <span
          aria-hidden
          className="absolute -left-[12px] bottom-3 size-0 border-y-[6px] border-r-[9px] border-y-transparent border-r-foreground"
        />
        <p className="font-bold">{msg.title}</p>
        <p className="mt-1 text-body-gray">{msg.body}</p>
        <div className="mt-2 flex justify-end gap-4 text-xs">
          <button
            type="button"
            className="underline underline-offset-2 hover:text-body-gray focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-foreground"
            onClick={onDisable}
          >
            不再提示
          </button>
          <button
            type="button"
            className="font-bold hover:text-body-gray focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-foreground"
            onClick={onDismiss}
          >
            知道了
          </button>
        </div>
      </div>
    </div>
  );
}

/** 輪到 `step` 時才出現。「知道了」關掉這一則；「不再提示」關閉全部引導（設定頁可重新開啟）。 */
export function GuideCoach({ step, className }: { step: GuideStepId; className?: string }) {
  const active = useActiveGuideStep() === step;
  const dismiss = useGuideStore((s) => s.dismiss);
  const setEnabled = useGuideStore((s) => s.setEnabled);
  if (!active) return null;
  return <GuideBubble step={step} className={className} onDismiss={() => dismiss(step)} onDisable={() => setEnabled(false)} />;
}
