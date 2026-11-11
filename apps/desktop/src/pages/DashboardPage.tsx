import { PageContainer } from '@/components/layout/PageContainer';
import { HeroTitle } from '@/features/dashboard/HeroTitle';
import { HowItWorks } from '@/features/dashboard/HowItWorks';
import { SystemNotice } from '@/features/dashboard/SystemNotice';
import { ImportCard } from '@/features/import/ImportCard';

export function DashboardPage() {
  return (
    <PageContainer>
      {/* 第一次使用必須先下載模型：提示放在最上方，不會漏看（2026-11-11 使用者建議）；一切正常時不顯示 */}
      <SystemNotice className="mb-8" />

      <section className="grid items-start gap-8 lg:grid-cols-2 lg:gap-12">
        <div className="min-w-0 lg:pt-4">
          <HeroTitle />
        </div>
        <ImportCard />
      </section>

      <HowItWorks className="mt-14" />
    </PageContainer>
  );
}
