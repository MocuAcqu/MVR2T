import type { ComponentType } from 'react';
import { AppShell } from '@/components/layout/AppShell';
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
  return (
    <SystemStatusProvider>
      <AppShell>
        <Page />
      </AppShell>
    </SystemStatusProvider>
  );
}
