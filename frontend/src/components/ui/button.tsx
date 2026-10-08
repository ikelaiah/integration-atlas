import * as React from "react";
import { Slot } from "@radix-ui/react-slot";
import { cva, type VariantProps } from "class-variance-authority";
import { cn } from "@/lib/utils";

const buttonVariants = cva(
  "inline-flex items-center justify-center gap-1.5 whitespace-nowrap rounded-[5px] font-medium transition-colors duration-150 disabled:pointer-events-none disabled:opacity-45 select-none",
  {
    variants: {
      variant: {
        default:
          "bg-accent text-white hover:bg-accent-strong active:bg-accent shadow-[0_1px_0_0_rgba(255,255,255,0.07)_inset]",
        secondary:
          "bg-surface-3 text-ink hover:bg-[#222c38] border border-line-strong",
        outline:
          "border border-line-strong bg-transparent text-ink-muted hover:text-ink hover:bg-surface-2 hover:border-[#3a4756]",
        ghost: "text-ink-muted hover:text-ink hover:bg-surface-2",
        destructive: "bg-danger/90 text-white hover:bg-danger",
        subtle: "bg-accent-soft text-accent-strong hover:bg-accent/20",
        link: "text-accent-strong underline-offset-2 hover:underline",
      },
      size: {
        xs: "h-6 px-2 text-[11px] rounded-[4px]",
        sm: "h-7 px-2.5 text-[12px]",
        md: "h-8 px-3 text-[13px]",
        lg: "h-9 px-4 text-[13px]",
        icon: "h-7 w-7",
        iconSm: "h-6 w-6",
      },
    },
    defaultVariants: { variant: "default", size: "sm" },
  },
);

export interface ButtonProps
  extends React.ButtonHTMLAttributes<HTMLButtonElement>,
    VariantProps<typeof buttonVariants> {
  asChild?: boolean;
}

export const Button = React.forwardRef<HTMLButtonElement, ButtonProps>(
  ({ className, variant, size, asChild = false, ...props }, ref) => {
    const Comp = asChild ? Slot : "button";
    return <Comp ref={ref} className={cn(buttonVariants({ variant, size }), className)} {...props} />;
  },
);
Button.displayName = "Button";

export { buttonVariants };
