import type { ReactNode } from 'react';
import { PageContainer } from '@/components/layout/PageContainer';
import { MONO_ANIMATIONS, type MonoAnimationName } from '@/components/mono/animations';
import { Mono } from '@/components/mono/Mono';
import { StatusDot } from '@/components/StatusDot';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { GuideBubble } from '@/features/guide/GuideCoach';

const COLORS = [
  ['Black', '#000000', 'bg-foreground text-background'],
  ['White', '#ffffff', 'bg-background text-foreground shadow-card'],
  ['Chip Gray', '#efefef', 'bg-chip'],
  ['Hover Gray', '#e2e2e2', 'bg-hover-gray'],
  ['Body Gray', '#4b4b4b', 'bg-body-gray text-background'],
  ['Muted Gray', '#afafaf', 'bg-muted-gray'],
] as const;

const TYPE = [
  ['Display 52 / 700', 'text-display', 'Your Media'],
  ['H1 36 / 700', 'text-h1', '工作區標題 Workspace'],
  ['H2 24 / 700', 'text-h2', '區塊標題 Section'],
  ['H3 20 / 700', 'text-h3', '卡片標題 Card title'],
  ['Large 18 / 500', 'text-lg font-medium', '導覽與重點文字'],
  ['Body 16 / 400', 'text-base', '一般內文，用於說明與表單。'],
  ['Caption 14', 'text-sm', '中繼資料與說明'],
  ['Micro 12', 'text-xs', '細項與備註'],
] as const;

function Section({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section className="mt-12">
      <h2 className="mb-4 text-h2">{title}</h2>
      {children}
    </section>
  );
}

/** Development-only reference page (hidden in production builds). */
export function StyleGuidePage() {
  return (
    <PageContainer>
      <h1 className="text-h1">設計規範</h1>
      <p className="mt-2 text-body-gray">僅開發模式顯示。用來檢查所有元件是否維持同一套風格。</p>

      <Section title="色彩">
        <div className="grid grid-cols-2 gap-3 md:grid-cols-3 xl:grid-cols-6">
          {COLORS.map(([name, hex, cls]) => (
            <div key={name} className={`flex h-24 flex-col justify-end rounded-lg p-3 text-sm ${cls}`}>
              <span className="font-medium">{name}</span>
              <span>{hex}</span>
            </div>
          ))}
        </div>
      </Section>

      <Section title="字級">
        <div className="flex flex-col">
          {TYPE.map(([label, cls, sample]) => (
            <div key={label} className="flex flex-wrap items-baseline justify-between gap-2 border-t border-chip py-3">
              <span className="w-40 shrink-0 text-sm text-body-gray">{label}</span>
              <span className={`${cls} min-w-0 flex-1`}>{sample}</span>
            </div>
          ))}
        </div>
      </Section>

      <Section title="按鈕">
        <div className="flex flex-col gap-4">
          <div className="flex flex-wrap items-center gap-3">
            <Button>主要</Button>
            <Button variant="secondary">次要</Button>
            <Button variant="outline">外框</Button>
            <Button variant="ghost">文字</Button>
            <Button disabled>停用</Button>
          </div>
          <div className="flex flex-wrap items-center gap-3">
            <Button size="sm">小</Button>
            <Button>預設</Button>
            <Button size="lg">大</Button>
          </div>
          <div className="flex rounded-xl bg-foreground p-4">
            <Button variant="inverse">黑底使用</Button>
          </div>
        </div>
      </Section>

      <Section title="輸入框">
        <div className="grid max-w-xl gap-3">
          <Input placeholder="一般" aria-label="一般" />
          <Input defaultValue="錯誤狀態（邊框加粗）" aria-invalid="true" aria-label="錯誤" />
          <Input placeholder="停用" disabled aria-label="停用" />
        </div>
      </Section>

      <Section title="卡片與標籤">
        <div className="grid gap-6 md:grid-cols-2">
          <Card>
            <CardHeader>
              <CardTitle>標準卡片 8px</CardTitle>
              <CardDescription>以極淡陰影區隔，不使用邊框。</CardDescription>
            </CardHeader>
            <CardContent className="flex flex-wrap gap-2">
              <Badge>預設</Badge>
              <Badge variant="solid">實心</Badge>
              <Badge variant="outline">外框</Badge>
            </CardContent>
          </Card>
          <Card featured>
            <CardHeader>
              <CardTitle>重點卡片 12px</CardTitle>
              <CardDescription>用於首頁主要操作區。</CardDescription>
            </CardHeader>
            <CardContent className="flex flex-col gap-2 text-sm">
              <span className="flex items-center gap-2"><StatusDot state="ok" />正常</span>
              <span className="flex items-center gap-2"><StatusDot state="fail" />未連線</span>
              <span className="flex items-center gap-2"><StatusDot state="pending" />檢查中</span>
            </CardContent>
          </Card>
        </div>
      </Section>

      <Section title="吉祥物 Mono">
        <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
          {(Object.keys(MONO_ANIMATIONS) as MonoAnimationName[]).map((name) => (
            <div key={name} className="flex flex-col items-center gap-2 rounded-lg bg-chip p-4 text-sm">
              <Mono animation={name} scale={3} />
              {name}
            </div>
          ))}
          <div className="flex flex-col items-center gap-2 rounded-lg bg-chip p-4 text-sm">
            <Mono scale={3} interactive />
            interactive（hover / click）
          </div>
        </div>
        <GuideBubble step="extract" className="mt-6 max-w-xl" onDismiss={() => {}} onDisable={() => {}} />
      </Section>
    </PageContainer>
  );
}
