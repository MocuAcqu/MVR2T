import { PageContainer } from '@/components/layout/PageContainer';
import { HeroTitle } from '@/features/dashboard/HeroTitle';
import { HardwareStatusCard } from '@/features/dashboard/HardwareStatusCard';
import { HowItWorks } from '@/features/dashboard/HowItWorks';
import { ModelStatusCard } from '@/features/dashboard/ModelStatusCard';
import { ImportCard } from '@/features/import/ImportCard';

export function DashboardPage() {
  return (
    <PageContainer>
      <section className="grid items-start gap-8 lg:grid-cols-2 lg:gap-12">
        <div className="min-w-0 lg:pt-4">
          <HeroTitle />
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
