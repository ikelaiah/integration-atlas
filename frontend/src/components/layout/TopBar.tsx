import { Search, Radar, GitBranch } from "lucide-react";
import { cn } from "@/lib/utils";
import { Kbd } from "@/components/ui/misc";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";

export interface TopBarProps {
  onOpenPalette: () => void;
  onOpenPathFinder: () => void;
  onOpenImpact: () => void;
  selectedName: string | null;
  className?: string;
}

export function TopBar({
  onOpenPalette,
  onOpenPathFinder,
  onOpenImpact,
  selectedName,
  className,
}: TopBarProps) {
  return (
    <header
      className={cn(
        "flex h-[52px] shrink-0 items-center gap-3 border-b border-line bg-surface px-4",
        className,
      )}
    >
      {/* search / command palette trigger */}
      <button
        type="button"
        onClick={onOpenPalette}
        className={cn(
          "group flex h-[30px] w-[300px] items-center gap-2 rounded-[6px] border border-line-strong",
          "bg-surface-2 px-2.5 text-left transition-colors",
          "hover:border-[#3a4756] hover:bg-surface-3",
        )}
      >
        <Search className="h-3.5 w-3.5 shrink-0 text-subtle" />
        <span className="flex-1 text-[12px] text-subtle">
          Search systems, tables, scripts…
        </span>
        <span className="flex items-center gap-0.5">
          <Kbd>Ctrl</Kbd>
          <Kbd>K</Kbd>
        </span>
      </button>

      {selectedName && (
        <div className="flex items-center gap-1.5 rounded-[5px] border border-line bg-surface-2 px-2 py-1">
          <span className="text-[10px] text-subtle">selected</span>
          <span className="max-w-[180px] truncate text-[11px] text-ink">{selectedName}</span>
        </div>
      )}

      <div className="ml-auto flex items-center gap-1.5">
        <Button variant="outline" size="sm" onClick={onOpenPathFinder}>
          <GitBranch className="h-3 w-3" />
          Find path
        </Button>
        <Button variant="subtle" size="sm" onClick={onOpenImpact}>
          <Radar className="h-3 w-3" />
          Impact
        </Button>
        <div className="ml-1 flex items-center gap-1.5">
          <Badge variant="subtle" size="xs">
            local-first
          </Badge>
          <div className="flex h-[26px] w-[26px] items-center justify-center rounded-full border border-line-strong bg-surface-2 text-[10px] font-semibold text-ink-muted">
            IA
          </div>
        </div>
      </div>
    </header>
  );
}
