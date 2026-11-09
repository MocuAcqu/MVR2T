import { PageContainer } from '@/components/layout/PageContainer';
import { HeroTitle } from '@/features/dashboard/HeroTitle';
import { HowItWorks } from '@/features/dashboard/HowItWorks';
import { SystemNotice } from '@/features/dashboard/SystemNotice';
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

      {/* 模型與這台電腦的詳細狀態已移到「模型管理」；首頁只在有問題時提醒 */}
      <SystemNotice className="mt-10" />

      <HowItWorks className="mt-14" />
    </PageContainer>
  );
}
