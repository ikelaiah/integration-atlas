import * as React from "react";
import { cn } from "@/lib/utils";

export const Input = React.forwardRef<HTMLInputElement, React.InputHTMLAttributes<HTMLInputElement>>(
  ({ className, type = "text", ...props }, ref) => (
    <input
      ref={ref}
      type={type}
      className={cn(
        "h-8 w-full rounded-[5px] border border-line-strong bg-surface-2 px-2.5 text-[12.5px] text-ink",
        "placeholder:text-subtle transition-colors",
        "hover:border-[#3a4756] focus:border-accent focus:outline-none focus:ring-1 focus:ring-accent/40",
        "disabled:cursor-not-allowed disabled:opacity-50",
        className,
      )}
      {...props}
    />
  ),
);
Input.displayName = "Input";

export function Label({
  className,
  ...props
}: React.LabelHTMLAttributes<HTMLLabelElement>) {
  return (
    <label
      className={cn(
        "text-[11px] font-medium uppercase tracking-[0.06em] text-subtle",
        className,
      )}
      {...props}
    />
  );
}

export function Textarea({
  className,
  ...props
}: React.TextareaHTMLAttributes<HTMLTextAreaElement>) {
  return (
    <textarea
      className={cn(
        "min-h-[70px] w-full rounded-[5px] border border-line-strong bg-surface-2 px-2.5 py-2 text-[12.5px] text-ink",
        "placeholder:text-subtle focus:border-accent focus:outline-none focus:ring-1 focus:ring-accent/40",
        className,
      )}
      {...props}
    />
  );
}
