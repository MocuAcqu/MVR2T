import { useEffect, type ComponentType } from 'react';
import { AppShell } from '@/components/layout/AppShell';
import { useBackgroundTaskEffects } from '@/features/media/backgroundEffects';
import { loadUiPrefs } from '@/features/settings/uiPrefs';
import { useLang } from '@/i18n';
import { SystemStatusProvider } from '@/hooks/useSystemStatus';
import { DashboardPage } from '@/pages/DashboardPage';
import { ModelsPage } from '@/pages/ModelsPage';
import { SettingsPage } from '@/pages/SettingsPage';
import { StyleGuidePage } from '@/pages/StyleGuidePage';
import { WorkspacePage } from '@/pages/WorkspacePage';
import { useUiStore, type PageId } from '@/stores/uiStore';

const PAGES: Record<PageId, ComponentType> = {
  dashboard: DashboardPage,
  workspace: WorkspacePage,
  models: ModelsPage,
  settings: SettingsPage,
  styleguide: StyleGuidePage,
};

export default function App() {
  const Page = PAGES[useUiStore((s) => s.page)];
  // 切換介面語言時重新繪製整個畫面（工作階段的資料在 store 中，不受影響）
  const lang = useLang((s) => s.lang);
  useBackgroundTaskEffects();
  useEffect(() => {
    void loadUiPrefs();
  }, []);
  return (
    <SystemStatusProvider>
      <AppShell key={lang}>
        <Page />
      </AppShell>
    </SystemStatusProvider>
  );
}
