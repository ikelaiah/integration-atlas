import * as React from "react";
import { cva, type VariantProps } from "class-variance-authority";
import { cn } from "@/lib/utils";

const badgeVariants = cva(
  "inline-flex items-center gap-1 rounded-[4px] border font-medium transition-colors",
  {
    variants: {
      variant: {
        default: "border-line-strong bg-surface-2 text-ink-muted",
        outline: "border-line-strong bg-transparent text-ink-muted",
        subtle: "border-transparent bg-surface-3 text-ink-muted",
        accent: "border-accent/30 bg-accent-soft text-accent-strong",
        success: "border-success/30 bg-success/10 text-success",
        warning: "border-warning/30 bg-warning/10 text-warning",
        danger: "border-danger/30 bg-danger/10 text-danger",
        info: "border-info/30 bg-info/10 text-info",
      },
      size: {
        xs: "h-[17px] px-1.5 text-[10px]",
        sm: "h-5 px-2 text-[11px]",
        md: "h-6 px-2.5 text-[12px]",
      },
    },
    defaultVariants: { variant: "default", size: "sm" },
  },
);

export interface BadgeProps
  extends React.HTMLAttributes<HTMLSpanElement>,
    VariantProps<typeof badgeVariants> {
  dotColor?: string;
}

export function Badge({ className, variant, size, dotColor, children, ...props }: BadgeProps) {
  return (
    <span className={cn(badgeVariants({ variant, size }), className)} {...props}>
      {dotColor ? (
        <span
          className="h-[5px] w-[5px] rounded-full shrink-0"
          style={{ backgroundColor: dotColor }}
          aria-hidden
        />
      ) : null}
      {children}
    </span>
  );
}

export { badgeVariants };
