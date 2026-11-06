import { forwardRef, type InputHTMLAttributes } from 'react';
import { cn } from '@/lib/utils';

/** 1px black border, 8px radius. Invalid state thickens the border (works without color). */
export const Input = forwardRef<HTMLInputElement, InputHTMLAttributes<HTMLInputElement>>(
  ({ className, type = 'text', ...props }, ref) => (
    <input
      ref={ref}
      type={type}
      className={cn(
        'flex h-11 w-full rounded-lg border border-foreground bg-background px-3 text-base text-foreground ' +
          'placeholder:text-body-gray focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-foreground ' +
          'focus-visible:ring-offset-2 focus-visible:ring-offset-background disabled:cursor-not-allowed ' +
          'disabled:opacity-40 aria-[invalid=true]:border-2',
        className,
      )}
      {...props}
    />
  ),
);
Input.displayName = 'Input';
