import { cva, type VariantProps } from 'class-variance-authority';
import type { HTMLAttributes } from 'react';
import { cn } from '@/lib/utils';

const badgeVariants = cva('inline-flex items-center gap-1 rounded-pill px-3 py-1 text-sm font-medium', {
  variants: {
    variant: {
      default: 'bg-chip text-foreground',
      solid: 'bg-foreground text-background',
      outline: 'border border-foreground text-foreground',
    },
  },
  defaultVariants: { variant: 'default' },
});

interface BadgeProps extends HTMLAttributes<HTMLSpanElement>, VariantProps<typeof badgeVariants> {}

export function Badge({ className, variant, ...props }: BadgeProps) {
  return <span className={cn(badgeVariants({ variant }), className)} {...props} />;
}
