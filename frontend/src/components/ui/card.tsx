import * as React from "react";
import { cn } from "@/lib/utils";

export function Card({ className, ...props }: React.HTMLAttributes<HTMLDivElement>) {
  return (
    <div
      className={cn("rounded-[10px] border border-line bg-surface panel-shadow", className)}
      {...props}
    />
  );
}

export function CardHeader({ className, ...props }: React.HTMLAttributes<HTMLDivElement>) {
  return <div className={cn("px-4 pt-3.5 pb-2.5", className)} {...props} />;
}

export function CardTitle({ className, ...props }: React.HTMLAttributes<HTMLHeadingElement>) {
  return (
    <h3
      className={cn("text-[13px] font-semibold text-ink leading-tight tracking-tight", className)}
      {...props}
    />
  );
}

export function CardDescription({ className, ...props }: React.HTMLAttributes<HTMLParagraphElement>) {
  return <p className={cn("text-[12px] text-muted leading-relaxed", className)} {...props} />;
}

export function CardContent({ className, ...props }: React.HTMLAttributes<HTMLDivElement>) {
  return <div className={cn("px-4 pb-4", className)} {...props} />;
}

export function CardFooter({ className, ...props }: React.HTMLAttributes<HTMLDivElement>) {
  return (
    <div className={cn("px-4 pb-3.5 flex items-center gap-2", className)} {...props} />
  );
}

/** A labelled key/value row used across detail panels. */
export function DetailRow({
  label,
  children,
  className,
}: {
  label: React.ReactNode;
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <div className={cn("flex items-start gap-3 py-[5px]", className)}>
      <div className="w-[104px] shrink-0 text-[11px] uppercase tracking-[0.06em] text-subtle pt-[1px]">
        {label}
      </div>
      <div className="flex-1 min-w-0 text-[12.5px] text-ink">{children}</div>
    </div>
  );
}
