import { PageContainer } from '@/components/layout/PageContainer';
import { HardwareStatusCard } from '@/features/dashboard/HardwareStatusCard';
import { HowItWorks } from '@/features/dashboard/HowItWorks';
import { ModelStatusCard } from '@/features/dashboard/ModelStatusCard';
import { ImportCard } from '@/features/import/ImportCard';

export function DashboardPage() {
  return (
    <PageContainer>
      <section className="grid items-start gap-8 lg:grid-cols-2 lg:gap-12">
        <div className="flex flex-col gap-4 lg:pt-4">
          <h1 className="text-h1 tracking-tight xl:text-display">
            Your Media.
            <br />
            Your Machine.
            <br />
            Your Knowledge.
          </h1>
          <p className="max-w-md text-base text-body-gray">
            在這台電腦上把影片與錄音轉成逐字稿、摘要和心智圖。模型下載一次後即可離線使用，檔案不會上傳。
          </p>
        </div>
        <ImportCard />
      </section>

      <section aria-label="系統狀態" className="mt-12 grid gap-6 md:grid-cols-2">
        <ModelStatusCard />
        <HardwareStatusCard />
      </section>

      <HowItWorks className="mt-14" />
    </PageContainer>
  );
}
