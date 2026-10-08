import * as React from "react";
import { cn } from "@/lib/utils";

export function Separator({
  className,
  orientation = "horizontal",
}: {
  className?: string;
  orientation?: "horizontal" | "vertical";
}) {
  return (
    <div
      role="separator"
      className={cn(
        "shrink-0 bg-line",
        orientation === "horizontal" ? "h-px w-full" : "w-px h-full",
        className,
      )}
    />
  );
}

export function Skeleton({ className }: { className?: string }) {
  return (
    <div
      className={cn("rounded-[4px] bg-surface-2 animate-pulse", className)}
      aria-hidden
    />
  );
}

export function Kbd({ children, className }: { children: React.ReactNode; className?: string }) {
  return (
    <kbd
      className={cn(
        "inline-flex h-[18px] min-w-[18px] items-center justify-center rounded-[4px] border border-line-strong",
        "bg-surface-2 px-1 font-mono text-[10px] text-ink-muted shadow-[0_1px_0_0_rgba(255,255,255,0.05)_inset]",
        className,
      )}
    >
      {children}
    </kbd>
  );
}

export function EmptyState({
  icon,
  title,
  description,
  action,
  className,
}: {
  icon?: React.ReactNode;
  title: string;
  description?: string;
  action?: React.ReactNode;
  className?: string;
}) {
  return (
    <div
      className={cn(
        "flex flex-col items-center justify-center gap-2.5 rounded-[10px] border border-dashed border-line px-6 py-10 text-center",
        className,
      )}
    >
      {icon && <div className="text-subtle">{icon}</div>}
      <div className="text-[13px] font-medium text-ink">{title}</div>
      {description && (
        <div className="max-w-[380px] text-[12px] leading-relaxed text-muted">{description}</div>
      )}
      {action && <div className="mt-1.5">{action}</div>}
    </div>
  );
}

export function ScrollArea({
  className,
  children,
}: {
  className?: string;
  children: React.ReactNode;
}) {
  return (
    <div className={cn("overflow-y-auto overflow-x-hidden", className)}>{children}</div>
  );
}

/** Small labelled stat used on the overview and scan screens. */
export function Stat({
  label,
  value,
  hint,
  accent,
  onClick,
}: {
  label: string;
  value: React.ReactNode;
  hint?: string;
  accent?: string;
  onClick?: () => void;
}) {
  const Comp = onClick ? "button" : "div";
  return (
    <Comp
      onClick={onClick}
      className={cn(
        "group flex flex-col gap-0.5 rounded-[8px] border border-line bg-surface px-3.5 py-3 text-left",
        onClick && "transition-colors hover:border-line-strong hover:bg-surface-2 cursor-pointer",
      )}
    >
      <div className="flex items-center gap-1.5">
        {accent && (
          <span className="h-[5px] w-[5px] rounded-full" style={{ backgroundColor: accent }} />
        )}
        <span className="text-[11px] uppercase tracking-[0.06em] text-subtle">{label}</span>
      </div>
      <div className="tabular text-[22px] font-semibold leading-tight text-ink tracking-tight">
        {value}
      </div>
      {hint && <div className="text-[11px] text-subtle">{hint}</div>}
    </Comp>
  );
}
