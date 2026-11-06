import { cva, type VariantProps } from 'class-variance-authority';
import { forwardRef, type ButtonHTMLAttributes } from 'react';
import { cn } from '@/lib/utils';

/** Pill-shaped buttons (999px) are a core part of the Uber look. Minimum height 36px, default 44px. */
export const buttonVariants = cva(
  'inline-flex items-center justify-center gap-2 whitespace-nowrap rounded-pill font-medium transition-colors ' +
    'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-foreground focus-visible:ring-offset-2 ' +
    'focus-visible:ring-offset-background disabled:pointer-events-none disabled:opacity-40 active:shadow-press ' +
    '[&_svg]:size-4 [&_svg]:shrink-0',
  {
    variants: {
      variant: {
        default: 'bg-foreground text-background hover:bg-body-gray', // primary black
        secondary: 'bg-chip text-foreground hover:bg-hover-gray',
        outline: 'border border-foreground bg-background text-foreground hover:bg-hover-light',
        ghost: 'bg-transparent text-foreground hover:bg-chip',
        inverse: 'bg-background text-foreground hover:bg-hover-gray', // for black surfaces
      },
      size: {
        sm: 'h-9 px-4 text-sm',
        default: 'h-11 px-5 text-base',
        lg: 'h-12 px-6 text-base',
        icon: 'h-11 w-11',
      },
    },
    defaultVariants: { variant: 'default', size: 'default' },
  },
);

export interface ButtonProps
  extends ButtonHTMLAttributes<HTMLButtonElement>,
    VariantProps<typeof buttonVariants> {}

export const Button = forwardRef<HTMLButtonElement, ButtonProps>(
  ({ className, variant, size, type = 'button', ...props }, ref) => (
    <button ref={ref} type={type} className={cn(buttonVariants({ variant, size }), className)} {...props} />
  ),
);
Button.displayName = 'Button';
