import { useEffect, useState } from "react";
import { ArrowLeftRight, GitBranch, Loader2, X } from "lucide-react";
import { api } from "@/lib/api";
import type { GraphNode } from "@/lib/types";
import { entityVisual } from "@/lib/entity-visuals";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogTitle } from "@/components/ui/dialog";
import { Input, Label } from "@/components/ui/input";
import { Kbd } from "@/components/ui/misc";

function useCandidates(workspaceId: string | null, query: string, selected: GraphNode | null, open: boolean) {
  const [items, setItems] = useState<GraphNode[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!open || !workspaceId || selected || !query.trim()) {
      setItems([]);
      setLoading(false);
      setError(null);
      return;
    }
    let cancelled = false;
    setItems([]);
    setLoading(true);
    setError(null);
    const timer = window.setTimeout(() => {
      api.search(workspaceId, query.trim(), 8)
        .then((result) => { if (!cancelled) setItems(result.hits.map((hit) => hit.entity)); })
        .catch((err: Error) => { if (!cancelled) setError(err.message); })
        .finally(() => { if (!cancelled) setLoading(false); });
    }, 200);
    return () => { cancelled = true; window.clearTimeout(timer); };
  }, [workspaceId, query, selected, open]);
  return { items, loading, error };
}

export function PathFinderDialog({
  workspaceId, open, onClose, onFind,
}: {
  workspaceId: string | null;
  open: boolean;
  onClose: () => void;
  onFind: (sourceId: string, targetId: string) => void;
}) {
  const [from, setFrom] = useState<GraphNode | null>(null);
  const [to, setTo] = useState<GraphNode | null>(null);
  const [fromQuery, setFromQuery] = useState("");
  const [toQuery, setToQuery] = useState("");
  const fromMatches = useCandidates(workspaceId, fromQuery, from, open);
  const toMatches = useCandidates(workspaceId, toQuery, to, open);

  useEffect(() => {
    setFrom(null);
    setTo(null);
    setFromQuery("");
    setToQuery("");
  }, [workspaceId]);

  if (!open) return null;

  const endpoint = (
    side: "from" | "to", query: string, selected: GraphNode | null,
    matches: ReturnType<typeof useCandidates>, otherId: string | undefined,
  ) => <div>
    <Label htmlFor={`path-${side}`}>{side === "from" ? "From" : "To"}</Label>
    <Input id={`path-${side}`} value={query} autoComplete="off" className="mt-1"
      placeholder={side === "from" ? "Search for the source" : "Search for the destination"}
      onChange={(event) => {
        if (side === "from") { setFromQuery(event.target.value); setFrom(null); }
        else { setToQuery(event.target.value); setTo(null); }
      }} />
    {query && !selected && <div className="mt-1 max-h-[150px] overflow-y-auto rounded-[5px] border border-line bg-surface">
      {matches.loading && <p className="flex items-center gap-1.5 px-2 py-2 text-[11px] text-muted"><Loader2 className="h-3 w-3 animate-spin" /> Searching…</p>}
      {matches.error && <p role="alert" className="px-2 py-2 text-[11px] text-danger">{matches.error}</p>}
      {!matches.loading && !matches.error && matches.items.filter((node) => node.id !== otherId).length === 0 &&
        <p className="px-2 py-2 text-[11px] text-muted">No matching active entities.</p>}
      {!matches.loading && matches.items.filter((node) => node.id !== otherId).map((node) =>
        <button key={node.id} type="button" className="flex w-full items-center gap-2 px-2 py-1.5 text-left hover:bg-surface-2"
          onClick={() => {
            if (side === "from") { setFrom(node); setFromQuery(node.name); }
            else { setTo(node); setToQuery(node.name); }
          }}>
          <span className="h-[6px] w-[6px] shrink-0 rounded-full" style={{ backgroundColor: entityVisual(node.entity_type).color }} />
          <span className="min-w-0 flex-1 truncate text-[11.5px] text-ink">{node.name}</span>
          <span className="text-[10px] text-subtle">{entityVisual(node.entity_type).label}</span>
        </button>)}
    </div>}
  </div>;

  return <Dialog open={open} onOpenChange={(nextOpen) => { if (!nextOpen) onClose(); }}>
    <DialogContent hideClose className="max-w-[440px] p-4">
      <div className="flex items-center gap-2"><GitBranch className="h-4 w-4 text-accent-strong" />
        <DialogTitle className="flex-1 text-[13px]">Find dependency path</DialogTitle>
        <Button variant="ghost" size="iconSm" onClick={onClose} aria-label="Close path finder"><X className="h-3.5 w-3.5" /></Button>
      </div>
      <DialogDescription className="mt-1.5 text-[11px]">Search the whole workspace. Graph filters do not limit the path search.</DialogDescription>
      <div className="mt-3 space-y-2.5">
        {endpoint("from", fromQuery, from, fromMatches, to?.id)}
        <div className="flex justify-center"><Button size="xs" variant="ghost" disabled={!from || !to}
          onClick={() => { setFrom(to); setTo(from); setFromQuery(to?.name ?? ""); setToQuery(from?.name ?? ""); }}>
          <ArrowLeftRight className="h-3 w-3" /> Swap endpoints
        </Button></div>
        {endpoint("to", toQuery, to, toMatches, from?.id)}
      </div>
      <div className="mt-4 flex items-center gap-2"><Button size="sm" disabled={!from || !to || from.id === to.id}
        onClick={() => { if (from && to) { onFind(from.id, to.id); onClose(); } }}>
        <GitBranch className="h-3 w-3" /> Find path
      </Button><Button variant="ghost" size="sm" onClick={onClose}>Cancel</Button>
        <span className="ml-auto text-[10px] text-subtle"><Kbd>esc</Kbd> to close</span>
      </div>
    </DialogContent>
  </Dialog>;
}
