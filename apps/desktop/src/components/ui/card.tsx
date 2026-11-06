import { forwardRef, type HTMLAttributes } from 'react';
import { cn } from '@/lib/utils';

interface CardProps extends HTMLAttributes<HTMLDivElement> {
  /** Featured cards use the larger 12px radius. */
  featured?: boolean;
}

/** Defined by a whisper-soft shadow, not a border. */
export const Card = forwardRef<HTMLDivElement, CardProps>(({ className, featured, ...props }, ref) => (
  <div
    ref={ref}
    className={cn('bg-background text-foreground shadow-card', featured ? 'rounded-xl' : 'rounded-lg', className)}
    {...props}
  />
));
Card.displayName = 'Card';

export const CardHeader = ({ className, ...props }: HTMLAttributes<HTMLDivElement>) => (
  <div className={cn('flex flex-col gap-1 p-6 pb-4', className)} {...props} />
);
export const CardTitle = ({ className, ...props }: HTMLAttributes<HTMLHeadingElement>) => (
  <h2 className={cn('text-h3', className)} {...props} />
);
export const CardDescription = ({ className, ...props }: HTMLAttributes<HTMLParagraphElement>) => (
  <p className={cn('text-sm text-body-gray', className)} {...props} />
);
export const CardContent = ({ className, ...props }: HTMLAttributes<HTMLDivElement>) => (
  <div className={cn('px-6 pb-6', className)} {...props} />
);
export const CardFooter = ({ className, ...props }: HTMLAttributes<HTMLDivElement>) => (
  <div className={cn('flex items-center gap-3 px-6 pb-6', className)} {...props} />
);
