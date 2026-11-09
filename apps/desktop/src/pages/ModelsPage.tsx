import { PageContainer } from '@/components/layout/PageContainer';
import { HardwareStatusCard } from '@/features/models/HardwareStatusCard';
import { ModelStatusCard } from '@/features/models/ModelStatusCard';

/** 模型管理：目前顯示模型安裝狀態與這台電腦的環境；程式內下載、驗證、刪除在 Phase 09 提供。 */
export function ModelsPage() {
  return (
    <PageContainer>
      <h1 className="text-h1">模型管理</h1>
      <p className="mt-1 text-body-gray">AI 模型與這台電腦的狀態。程式內的下載、驗證與刪除功能將在後續版本提供。</p>
      <div className="mt-6 grid items-start gap-6 md:grid-cols-2">
        <ModelStatusCard />
        <HardwareStatusCard />
      </div>
    </PageContainer>
  );
}
