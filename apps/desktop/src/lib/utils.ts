import { clsx, type ClassValue } from 'clsx';
import { extendTailwindMerge } from 'tailwind-merge';

// Teach tailwind-merge our custom tokens (see tailwind.config.ts), otherwise `text-h3` would be
// treated as a text color and wrongly conflict with classes like `text-body-gray`.
const twMerge = extendTailwindMerge({
  extend: {
    classGroups: {
      'font-size': [{ text: ['display', 'h1', 'h2', 'h3'] }],
      shadow: [{ shadow: ['card', 'raised', 'float', 'press'] }],
      rounded: [{ rounded: ['pill'] }],
    },
  },
});

/** Merge class names; later Tailwind classes win over earlier conflicting ones. */
export function cn(...inputs: ClassValue[]): string {
  return twMerge(clsx(inputs));
}
