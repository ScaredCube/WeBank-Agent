import { type TextareaHTMLAttributes, forwardRef } from 'react'

import { cn } from '@/lib/utils'

export const Textarea = forwardRef<HTMLTextAreaElement, TextareaHTMLAttributes<HTMLTextAreaElement>>(
  ({ className, ...props }, ref) => (
    <textarea
      ref={ref}
      className={cn(
        'w-full resize-none bg-transparent text-[15px] leading-relaxed text-ink outline-none placeholder:text-muted/50',
        className,
      )}
      {...props}
    />
  ),
)
Textarea.displayName = 'Textarea'
