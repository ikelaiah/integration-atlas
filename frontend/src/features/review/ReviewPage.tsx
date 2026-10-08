import { useCallback, useEffect, useState } from "react";
import { Check, ChevronLeft, ChevronRight, RefreshCw, ShieldCheck, X } from "lucide-react";
import { api } from "@/lib/api";
import type { RelationshipDetail, ReviewStatus } from "@/lib/types";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent } from "@/components/ui/card";
import { Label, Textarea } from "@/components/ui/input";
import { EmptyState, Skeleton } from "@/components/ui/misc";

const FILTERS: ReviewStatus[] = ["proposed", "confirmed", "rejected"];

export function ReviewPage({ workspaceId }: { workspaceId: string | null }) {
  const [status, setStatus] = useState<ReviewStatus>("proposed");
  const [offset, setOffset] = useState(0);
  const [items, setItems] = useState<RelationshipDetail[]>([]);
  const [total, setTotal] = useState(0);
  const [selected, setSelected] = useState<string | null>(null);
  const [note, setNote] = useState("");
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(() => {
    if (!workspaceId) return;
    setLoading(true);
    setError(null);
    api.review.list(workspaceId, status, offset)
      .then((page) => { setItems(page.items); setTotal(page.total); })
      .catch((err: Error) => setError(err.message))
      .finally(() => setLoading(false));
  }, [workspaceId, status, offset]);

  useEffect(() => { load(); }, [load]);
  const current = items.find((item) => item.id === selected)
    ?? items.find((item) => item.evidence.length > 0)
    ?? items[0] ?? null;

  const decide = (verdict: ReviewStatus) => {
    if (!current) return;
    setSaving(true);
    setError(null);
    api.review.decide(current.id, verdict, note)
      .then(() => { setNote(""); setSelected(null); load(); })
      .catch((err: Error) => setError(err.message))
      .finally(() => setSaving(false));
  };

  return <div className="h-full overflow-y-auto">
    <div className="mx-auto max-w-[1180px] px-6 py-7">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div><h1 className="text-[21px] font-semibold tracking-tight text-ink">Relationship review</h1>
          <p className="mt-1 text-[12px] text-muted">Inspect source evidence, then confirm or reject discovered connections.</p></div>
        <Button variant="ghost" size="xs" onClick={load}><RefreshCw className="h-3 w-3" /> Refresh</Button>
      </div>
      <div role="tablist" aria-label="Review status" className="mt-5 flex gap-1 border-b border-line">
        {FILTERS.map((filter) => <button type="button" role="tab" aria-selected={status === filter} key={filter}
          onClick={() => { setStatus(filter); setOffset(0); setSelected(null); setNote(""); }}
          className={`px-3 py-2 text-[12px] capitalize ${status === filter ? "border-b-2 border-accent text-ink" : "text-muted hover:text-ink"}`}>{filter}</button>)}
      </div>
      {error && <p role="alert" className="mt-3 text-[12px] text-danger">{error}</p>}
      {loading ? <Skeleton className="mt-4 h-40" /> : items.length === 0 ?
        <div className="mt-4"><EmptyState icon={<ShieldCheck className="h-5 w-5" />} title={`No ${status} relationships`} description="Run a scan to discover relationships, or choose another status." /></div> :
        <div className="mt-4 grid gap-3 lg:grid-cols-[minmax(260px,0.85fr)_minmax(320px,1.15fr)]">
          <div className="space-y-1.5" aria-label="Relationships">
            {items.map((item) => <button key={item.id} type="button" onClick={() => { setSelected(item.id); setNote(""); }}
              aria-current={current?.id === item.id}
              className={`w-full rounded-[7px] border px-3 py-2.5 text-left ${current?.id === item.id ? "border-accent/50 bg-surface-2" : "border-line bg-surface hover:bg-surface-2"}`}>
              <div className="flex items-center gap-1.5 text-[12px] font-medium text-ink"><span className="truncate">{item.source.name}</span><span className="text-subtle">→</span><span className="truncate">{item.target.name}</span></div>
              <div className="mt-1 flex gap-2 text-[10.5px] text-muted"><span>{item.relationship_type.replaceAll("_", " ")}</span><span>·</span><span>{item.confidence} confidence</span></div>
            </button>)}
          </div>
          {current && <Card><CardContent>
            <div className="flex flex-wrap items-center gap-2"><h2 className="text-[14px] font-semibold text-ink">{current.source.name} → {current.target.name}</h2><Badge variant="subtle" size="xs">{current.review_status}</Badge></div>
            <p className="mt-1 text-[11px] text-muted">{current.relationship_type.replaceAll("_", " ")} · {current.confidence} confidence</p>
            <h3 className="mt-4 text-[11px] font-semibold uppercase tracking-wide text-subtle">Evidence</h3>
            {current.evidence.length ? <ul className="mt-2 space-y-2">{current.evidence.map((evidence) => <li key={evidence.id} className="rounded-[5px] border border-line bg-surface-2 p-2.5">
              <div className="break-all text-[10px] text-muted">{evidence.source_path || evidence.parser}{evidence.line_start ? `:${evidence.line_start}` : ""}</div>
              {evidence.snippet && <pre className="mt-1 max-h-32 overflow-auto whitespace-pre-wrap break-words text-[11px] text-ink">{evidence.snippet}</pre>}
            </li>)}</ul> : <p className="mt-2 text-[11px] text-muted">No source excerpt recorded.</p>}
            <div className="mt-4"><Label htmlFor="review-note">Review note (optional)</Label><Textarea id="review-note" value={note} onChange={(event) => setNote(event.target.value)} maxLength={5000} placeholder="Why did you make this decision?" className="mt-1" /></div>
            <div className="mt-3 flex gap-2"><Button size="sm" onClick={() => decide("confirmed")} disabled={saving}><Check className="h-3.5 w-3.5" /> Confirm</Button><Button size="sm" variant="outline" onClick={() => decide("rejected")} disabled={saving}><X className="h-3.5 w-3.5" /> Reject</Button></div>
          </CardContent></Card>}
        </div>}
      {total > 50 && <div className="mt-4 flex items-center justify-end gap-2 text-[11px] text-muted"><span>{offset + 1}–{Math.min(offset + 50, total)} of {total}</span><Button size="iconSm" variant="ghost" title="Previous page" disabled={offset === 0} onClick={() => { setOffset(Math.max(0, offset - 50)); setSelected(null); }}><ChevronLeft className="h-3.5 w-3.5" /></Button><Button size="iconSm" variant="ghost" title="Next page" disabled={offset + 50 >= total} onClick={() => { setOffset(offset + 50); setSelected(null); }}><ChevronRight className="h-3.5 w-3.5" /></Button></div>}
    </div>
  </div>;
}
