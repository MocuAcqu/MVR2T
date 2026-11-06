import type { ReactNode } from 'react';
import { cn } from '@/lib/utils';

/** Max content width 1136px, centered (Uber container). */
export function PageContainer({ children, className }: { children: ReactNode; className?: string }) {
  return (
    <div className={cn('mx-auto w-full max-w-[1136px] px-4 py-8 sm:px-6 lg:px-8 lg:py-12', className)}>
      {children}
    </div>
  );
}
