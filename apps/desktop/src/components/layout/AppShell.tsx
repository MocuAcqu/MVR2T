import { useEffect, type ReactNode } from 'react';
import { Mono } from '@/components/mono/Mono';
import { describeBackend, StatusDot } from '@/components/StatusDot';
import { useSystemStatus } from '@/hooks/useSystemStatus';
import { cn } from '@/lib/utils';
import { useUiStore, type PageId } from '@/stores/uiStore';

const NAV_ITEMS: { id: PageId; label: string }[] = [
  { id: 'dashboard', label: '首頁' },
  { id: 'workspace', label: '工作區' },
  { id: 'models', label: '模型管理' },
  { id: 'settings', label: '設定' },
  ...(import.meta.env.DEV ? [{ id: 'styleguide' as const, label: '設計規範' }] : []),
];

const focusRing =
  'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-foreground focus-visible:ring-offset-2 focus-visible:ring-offset-background';

/** Sticky white header with pill navigation, content area, and a black status footer. */
export function AppShell({ children }: { children: ReactNode }) {
  const page = useUiStore((s) => s.page);
  const setPage = useUiStore((s) => s.setPage);
  const { app, backend } = useSystemStatus();
  const status = describeBackend(backend);

  // Braces matter: newer Chromium returns a Promise from scrollTo(), and returning it from an
  // effect makes React treat it as the cleanup function ("destroy is not a function" crash).
  useEffect(() => {
    window.scrollTo(0, 0);
  }, [page]);

  return (
    <div className="flex min-h-screen flex-col">
      <header className="sticky top-0 z-10 border-b border-chip bg-background">
        <div className="mx-auto flex h-16 w-full max-w-[1136px] items-center gap-4 px-4 sm:px-6 lg:px-8">
          {/* 吉祥物 Mono：滑鼠移過去會好奇地聞聞，點一下會 Q 彈一下 */}
          <Mono scale={1} interactive label="Mono（吉祥物）" className="-my-1" />
          <button
            onClick={() => setPage('dashboard')}
            aria-label="MVR2T，回到首頁"
            className={cn('rounded-pill text-2xl font-bold tracking-tight', focusRing)}
          >
            MVR2T
          </button>
          <nav aria-label="主要導覽" className="flex min-w-0 flex-1 gap-2 overflow-x-auto p-1">
            {NAV_ITEMS.map((item) => (
              <button
                key={item.id}
                onClick={() => setPage(item.id)}
                aria-current={page === item.id ? 'page' : undefined}
                className={cn(
                  'shrink-0 rounded-pill px-4 py-2 text-sm font-medium transition-colors',
                  focusRing,
                  page === item.id ? 'bg-foreground text-background' : 'bg-chip hover:bg-hover-gray',
                )}
              >
                {item.label}
              </button>
            ))}
          </nav>
          <div role="status" className="hidden shrink-0 items-center gap-2 text-sm font-medium sm:flex">
            <StatusDot state={status.state} />
            {status.label}
          </div>
        </div>
      </header>

      <main className="flex-1">{children}</main>

      <footer className="bg-foreground text-muted-gray">
        <div className="mx-auto flex w-full max-w-[1136px] flex-wrap items-center justify-between gap-x-6 gap-y-1 px-4 py-4 text-sm sm:px-6 lg:px-8">
          <p>所有處理都在這台電腦完成，檔案不會上傳。</p>
          {app.status === 'electron' ? <p>版本 {app.info.version}</p> : null}
        </div>
      </footer>
    </div>
  );
}
