import * as React from "react";
import * as TabsPrimitive from "@radix-ui/react-tabs";
import { cn } from "@/lib/utils";

export const Tabs = TabsPrimitive.Root;

export const TabsList = React.forwardRef<
  React.ElementRef<typeof TabsPrimitive.List>,
  React.ComponentPropsWithoutRef<typeof TabsPrimitive.List>
>(({ className, ...props }, ref) => (
  <TabsPrimitive.List
    ref={ref}
    className={cn(
      "inline-flex items-center gap-0.5 rounded-[6px] bg-surface-2 p-[3px] border border-line",
      className,
    )}
    {...props}
  />
));
TabsList.displayName = "TabsList";

export const TabsTrigger = React.forwardRef<
  React.ElementRef<typeof TabsPrimitive.Trigger>,
  React.ComponentPropsWithoutRef<typeof TabsPrimitive.Trigger>
>(({ className, ...props }, ref) => (
  <TabsPrimitive.Trigger
    ref={ref}
    className={cn(
      "inline-flex items-center justify-center gap-1.5 rounded-[4px] px-2.5 h-6.5 text-[11.5px] font-medium",
      "text-ink-muted transition-colors whitespace-nowrap",
      "hover:text-ink data-[state=active]:bg-surface-3 data-[state=active]:text-ink",
      "data-[state=active]:shadow-[0_1px_2px_rgba(0,0,0,0.25)] disabled:opacity-40",
      className,
    )}
    {...props}
  />
));
TabsTrigger.displayName = "TabsTrigger";

export const TabsContent = React.forwardRef<
  React.ElementRef<typeof TabsPrimitive.Content>,
  React.ComponentPropsWithoutRef<typeof TabsPrimitive.Content>
>(({ className, ...props }, ref) => (
  <TabsPrimitive.Content
    ref={ref}
    className={cn("mt-3 focus-visible:outline-none", className)}
    {...props}
  />
));
TabsContent.displayName = "TabsContent";

/** Underlined tab style used in the entity panel. */
export function UnderlineTabs({
  tabs,
  value,
  onChange,
  className,
}: {
  tabs: { value: string; label: string; count?: number }[];
  value: string;
  onChange: (value: string) => void;
  className?: string;
}) {
  return (
    <div className={cn("flex items-center gap-0 border-b border-line", className)}>
      {tabs.map((tab) => {
        const active = tab.value === value;
        return (
          <button
            key={tab.value}
            type="button"
            onClick={() => onChange(tab.value)}
            className={cn(
              "relative px-2.5 py-1.5 text-[11.5px] font-medium transition-colors",
              active ? "text-ink" : "text-subtle hover:text-ink-muted",
            )}
          >
            <span className="inline-flex items-center gap-1.5">
              {tab.label}
              {tab.count !== undefined && (
                <span
                  className={cn(
                    "tabular text-[10px] rounded-[3px] px-1 py-[0.5px]",
                    active ? "bg-accent-soft text-accent-strong" : "bg-surface-2 text-subtle",
                  )}
                >
                  {tab.count}
                </span>
              )}
            </span>
            {active && (
              <span className="absolute left-1.5 right-1.5 -bottom-px h-[1.5px] rounded-full bg-accent" />
            )}
          </button>
        );
      })}
    </div>
  );
}
