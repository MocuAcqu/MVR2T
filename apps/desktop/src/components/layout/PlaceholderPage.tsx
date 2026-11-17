import { PageContainer } from '@/components/layout/PageContainer';
import { Badge } from '@/components/ui/badge';
import { Card, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { t } from '@/i18n';

/** Honest stand-in for pages that are built in later phases. */
export function PlaceholderPage({ title, description }: { title: string; description: string }) {
  return (
    <PageContainer>
      <h1 className="text-h1">{title}</h1>
      <Card className="mt-6 max-w-xl">
        <CardHeader className="pb-6">
          <Badge className="mb-2 self-start">{t('開發中')}</Badge>
          <CardTitle>{t('{0}還沒開放', title)}</CardTitle>
          <CardDescription>{description}</CardDescription>
        </CardHeader>
      </Card>
    </PageContainer>
  );
}
