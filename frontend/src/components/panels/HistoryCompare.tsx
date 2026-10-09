import { useEffect, useMemo, useRef, useState } from "react";
import { ArrowRight, GitCompareArrows, Loader2 } from "lucide-react";
import { api } from "@/lib/api";
import type {
  CheckpointPhase, GraphComparison, HistoricalChange, ScanCheckpoint, ScanProgress,
} from "@/lib/types";
import { cn, formatNumber } from "@/lib/utils";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input, Label } from "@/components/ui/input";

type Choice = { scan: ScanCheckpoint; phase: CheckpointPhase; value: string; time: number };
type ChangeKind = "entity" | "relationship";
type ChangeAction = "added" | "updated" | "removed";

function choicesFor(checkpoints: ScanCheckpoint[]): Choice[] {
  return checkpoints.flatMap((scan) => (["after", "before"] as CheckpointPhase[]).map((phase) => ({
    scan, phase, value: `${scan.scan_id}:${phase}`,
    time: Date.parse(phase === "after" ? scan.finished_at ?? "" : scan.started_at ?? ""),
  })));
}

function choiceLabel(choice: Choice): string {
  const path = choice.scan.root_path.split(/[\\/]/).filter(Boolean).at(-1) ?? choice.scan.root_path;
  const stamp = choice.phase === "after" ? choice.scan.finished_at : choice.scan.started_at;
  const date = stamp ? new Date(stamp).toLocaleString() : "Unknown time";
  return `${choice.phase === "after" ? "After" : "Before"} · ${date} · ${path}`;
}

function formatField(field: string): string {
  return field.replaceAll("_id", "").replaceAll("_", " ");
}

function fieldValue(row: Record<string, unknown> | null, field: string): string {
  if (!row) return "—";
  const value = field === "source_id" ? row.source_name
    : field === "target_id" ? row.target_name : row[field];
  if (value === null || value === undefined || value === "") return "—";
  if (typeof value === "boolean") return value ? "Yes" : "No";
  return String(value);
}

function ChangeDetails({ change }: { change: HistoricalChange }) {
  const fields = change.action === "updated" ? change.changed_fields
    : Object.keys(change.after ?? change.before ?? {}).filter((field) =>
      field !== "source_name" && field !== "target_name");
  return <div className="border-t border-line bg-surface-2 px-3 py-3">
    {change.before_name && change.after_name && change.before_name !== change.after_name &&
      <p className="mb-2 text-[11px] text-muted">{change.before_name} <ArrowRight className="mx-1 inline h-3 w-3" /> {change.after_name}</p>}
    <div className="overflow-x-auto">
      <table className="w-full min-w-[420px] table-fixed text-left text-[11px]">
        <thead className="text-[10px] uppercase tracking-[0.06em] text-subtle">
          <tr><th className="w-[24%] pb-1 font-medium">Field</th><th className="w-[38%] pb-1 font-medium">Before</th><th className="pb-1 font-medium">After</th></tr>
        </thead>
        <tbody>
          {fields.map((field) => <tr key={field} className="border-t border-line/70 align-top">
            <th className="py-1.5 pr-2 font-medium capitalize text-ink-muted">{formatField(field)}</th>
            <td className="break-words py-1.5 pr-3 text-muted">{fieldValue(change.before, field)}</td>
            <td className="break-words py-1.5 text-ink">{fieldValue(change.after, field)}</td>
          </tr>)}
        </tbody>
      </table>
    </div>
  </div>;
}

export function HistoryCompare({ workspaceId, scans }: {
  workspaceId: string | null;
  scans: ScanProgress[];
}) {
  const [checkpoints, setCheckpoints] = useState<ScanCheckpoint[]>([]);
  const [loadingCheckpoints, setLoadingCheckpoints] = useState(true);
  const [loadingOlder, setLoadingOlder] = useState(false);
  const [hasOlder, setHasOlder] = useState(false);
  const [checkpointError, setCheckpointError] = useState<string | null>(null);
  const checkpointSeq = useRef(0);
  const [from, setFrom] = useState("");
  const [to, setTo] = useState("");
  const [kind, setKind] = useState<ChangeKind | "">("");
  const [action, setAction] = useState<ChangeAction | "">("");
  const [search, setSearch] = useState("");
  const [query, setQuery] = useState("");
  const [offset, setOffset] = useState(0);
  const [result, setResult] = useState<GraphComparison | null>(null);
  const [loadingResult, setLoadingResult] = useState(false);
  const [compareError, setCompareError] = useState<string | null>(null);
  const [expanded, setExpanded] = useState<string | null>(null);

  useEffect(() => {
    setFrom(""); setTo(""); setResult(null); setOffset(0);
  }, [workspaceId]);

  useEffect(() => {
    if (!workspaceId) { setCheckpoints([]); setLoadingCheckpoints(false); return; }
    const seq = ++checkpointSeq.current;
    setLoadingCheckpoints(true);
    setCheckpointError(null);
    api.scans.checkpoints(workspaceId)
      .then((rows) => {
        if (seq !== checkpointSeq.current) return;
        setCheckpoints(rows);
        setHasOlder(rows.length === 500);
        const options = choicesFor(rows);
        setFrom((previous) => options.some((item) => item.value === previous)
          ? previous : options.find((item) => item.phase === "before")?.value ?? "");
        setTo((previous) => options.some((item) => item.value === previous)
          ? previous : options.find((item) => item.phase === "after")?.value ?? "");
      })
      .catch((error: Error) => { if (seq === checkpointSeq.current) setCheckpointError(error.message); })
      .finally(() => { if (seq === checkpointSeq.current) setLoadingCheckpoints(false); });
    return () => { checkpointSeq.current += 1; };
  }, [workspaceId, scans]);

  const loadOlder = () => {
    if (!workspaceId || loadingOlder) return;
    const seq = checkpointSeq.current;
    setLoadingOlder(true);
    setCheckpointError(null);
    api.scans.checkpoints(workspaceId, checkpoints.length)
      .then((rows) => {
        if (seq !== checkpointSeq.current) return;
        setCheckpoints((previous) => [...previous, ...rows]);
        setHasOlder(rows.length === 500);
      })
      .catch((error: Error) => { if (seq === checkpointSeq.current) setCheckpointError(error.message); })
      .finally(() => { if (seq === checkpointSeq.current) setLoadingOlder(false); });
  };

  useEffect(() => {
    const timer = window.setTimeout(() => setQuery(search.trim()), 250);
    return () => window.clearTimeout(timer);
  }, [search]);

  const options = useMemo(() => choicesFor(checkpoints), [checkpoints]);
  const fromChoice = options.find((item) => item.value === from);
  const toChoice = options.find((item) => item.value === to);
  const validOrder = Boolean(fromChoice && toChoice && fromChoice.time < toChoice.time);
  const legacyCount = scans.filter((scan) => scan.scan.status === "completed"
    && !checkpoints.some((item) => item.scan_id === scan.scan.id)).length;

  useEffect(() => {
    if (!workspaceId || !fromChoice || !toChoice || !validOrder) {
      setResult(null);
      return;
    }
    let cancelled = false;
    setLoadingResult(true);
    setCompareError(null);
    if (offset === 0) setResult(null);
    api.scans.compare({
      workspace_id: workspaceId,
      from_scan_id: fromChoice.scan.scan_id, from_phase: fromChoice.phase,
      to_scan_id: toChoice.scan.scan_id, to_phase: toChoice.phase,
      kind: kind || undefined, action: action || undefined, q: query || undefined,
      offset,
    }).then((page) => {
      if (cancelled) return;
      setResult((previous) => offset === 0 || !previous ? page
        : { ...page, changes: [...previous.changes, ...page.changes] });
    }).catch((error: Error) => { if (!cancelled) setCompareError(error.message); })
      .finally(() => { if (!cancelled) setLoadingResult(false); });
    return () => { cancelled = true; };
  }, [workspaceId, from, to, kind, action, query, offset, validOrder]);

  const resetPage = () => { setOffset(0); setExpanded(null); setResult(null); };
  const selectClass = "mt-1 h-9 w-full rounded-[5px] border border-line-strong bg-surface px-2 text-[11.5px] text-ink outline-none focus-visible:ring-2 focus-visible:ring-accent/50";
  const filterClass = (active: boolean) => cn(
    "rounded-[5px] border px-2 py-1 text-[10.5px] transition-colors",
    active ? "border-accent/40 bg-accent-soft text-accent-strong"
      : "border-line-strong text-ink-muted hover:bg-surface-2",
  );

  return <Card className="mt-6">
    <CardHeader><div className="flex items-center gap-1.5">
      <GitCompareArrows className="h-3.5 w-3.5 text-accent-strong" />
      <CardTitle>Compare graph history</CardTitle>
      <Badge variant="subtle" size="xs" className="ml-auto">{checkpoints.length} checkpointed scans</Badge>
    </div></CardHeader>
    <CardContent>
      <p className="text-[11px] leading-relaxed text-muted">Compare saved graph states, including rejected relationships. This reads checkpoints without scanning files or changing your current Atlas.</p>
      {loadingCheckpoints && <p className="mt-3 flex items-center gap-2 text-[11px] text-muted"><Loader2 className="h-3 w-3 animate-spin" /> Loading checkpoints…</p>}
      {checkpointError && <p role="alert" className="mt-3 text-[11px] text-danger">{checkpointError}</p>}
      {!loadingCheckpoints && !checkpointError && checkpoints.length === 0 &&
        <p className="mt-3 rounded-[6px] border border-line bg-surface-2 p-3 text-[11px] text-muted">
          {scans.length ? "Earlier scans retain their per-scan diffs, but have no graph checkpoints. Apply a new scan to compare its before and after states."
            : "Apply a scan to create your first before and after graph checkpoints."}
        </p>}
      {!loadingCheckpoints && checkpoints.length > 0 && <>
        {legacyCount > 0 && <p className="mt-3 text-[10.5px] text-subtle">{legacyCount} earlier completed scan{legacyCount === 1 ? " has" : "s have"} no saved checkpoint and remain available in Scan history.</p>}
        <div className="mt-3 grid gap-2 md:grid-cols-[1fr_auto_1fr] md:items-end">
          <div><Label htmlFor="history-from">Earlier checkpoint</Label>
            <select id="history-from" value={from} className={selectClass} onChange={(event) => { setFrom(event.target.value); resetPage(); }}>
              {options.map((item) => <option value={item.value} key={item.value}>{choiceLabel(item)}</option>)}
            </select></div>
          <ArrowRight className="mx-auto hidden h-4 w-4 text-subtle md:mb-2 md:block" />
          <div><Label htmlFor="history-to">Later checkpoint</Label>
            <select id="history-to" value={to} className={selectClass} onChange={(event) => { setTo(event.target.value); resetPage(); }}>
              {options.map((item) => <option value={item.value} key={item.value}>{choiceLabel(item)}</option>)}
            </select></div>
        </div>
        {hasOlder && <Button variant="ghost" size="xs" className="mt-2" onClick={loadOlder} disabled={loadingOlder}>
          {loadingOlder && <Loader2 className="h-3 w-3 animate-spin" />} Load older checkpoints
        </Button>}
        {!validOrder && <p role="alert" className="mt-2 text-[11px] text-danger">Choose an earlier checkpoint on the left and a later checkpoint on the right.</p>}
        {loadingResult && !result && <p className="mt-4 flex items-center gap-2 text-[11px] text-muted"><Loader2 className="h-3 w-3 animate-spin" /> Comparing saved graphs…</p>}
        {compareError && <p role="alert" className="mt-3 text-[11px] text-danger">{compareError}</p>}
        {result && <>
          <div className="mt-4 grid gap-2 sm:grid-cols-2">
            {(["entities", "relationships"] as const).map((item) => <div key={item} className="rounded-[7px] border border-line bg-surface-2 p-3">
              <div className="text-[10px] uppercase tracking-[0.07em] text-subtle">{item}</div>
              <div className="mt-1 flex items-baseline gap-2 text-[16px] font-semibold tabular text-ink">
                {formatNumber(result.from_counts[item])}<ArrowRight className="h-3.5 w-3.5 text-subtle" />{formatNumber(result.to_counts[item])}
              </div>
              <div className="mt-1 flex flex-wrap gap-x-3 gap-y-0.5 text-[10.5px]">
                <span className="text-success">+{result.counts[item].added} added</span>
                <span className="text-accent-strong">{result.counts[item].updated} changed</span>
                <span className="text-danger">−{result.counts[item].removed} retired</span>
              </div>
            </div>)}
          </div>
          <div className="mt-4 flex flex-wrap items-center gap-1.5">
            {(["", "entity", "relationship"] as const).map((value) => <button key={value || "all"} type="button" aria-pressed={kind === value}
              className={filterClass(kind === value)} onClick={() => { setKind(value); resetPage(); }}>
              {value === "" ? "All" : value === "entity" ? "Entities" : "Relationships"}
            </button>)}
            <span className="mx-1 h-4 border-l border-line" />
            {(["", "added", "updated", "removed"] as const).map((value) => <button key={value || "all-actions"} type="button" aria-pressed={action === value}
              className={filterClass(action === value)} onClick={() => { setAction(value); resetPage(); }}>
              {value === "" ? "Any change" : value === "removed" ? "Retired" : value === "updated" ? "Changed" : "Added"}
            </button>)}
            <Input aria-label="Search changed names" value={search} placeholder="Search changes" className="ml-auto h-7 w-full sm:w-[180px]"
              onChange={(event) => { setSearch(event.target.value); resetPage(); }} />
          </div>
          <p className="mt-2 text-[10px] text-subtle">{formatNumber(result.filtered_total)} matching changes · {formatNumber(result.total)} net changes</p>
          <div className="mt-2 overflow-hidden rounded-[7px] border border-line">
            {result.changes.length === 0 && <p className="p-3 text-[11px] text-muted">{result.total === 0 ? "These checkpoints have the same graph." : "No changes match the selected filters."}</p>}
            {result.changes.map((change) => <div key={`${change.kind}-${change.id}`} className="border-b border-line last:border-b-0">
              <button type="button" aria-expanded={expanded === `${change.kind}-${change.id}`}
                onClick={() => setExpanded((current) => current === `${change.kind}-${change.id}` ? null : `${change.kind}-${change.id}`)}
                className="flex w-full items-center gap-2 px-3 py-2.5 text-left hover:bg-surface-2">
                <span className={cn("w-[54px] shrink-0 text-[10px] capitalize", change.action === "removed" ? "text-danger" : change.action === "added" ? "text-success" : "text-accent-strong")}>{change.action === "removed" ? "retired" : change.action === "updated" ? "changed" : "added"}</span>
                <span className="min-w-0 flex-1 truncate text-[11.5px] text-ink" title={change.name}>{change.name}</span>
                <span className="hidden shrink-0 text-[10px] capitalize text-subtle sm:block">{change.type.replaceAll("_", " ")}</span>
                <span className="shrink-0 text-[10px] text-subtle">{expanded === `${change.kind}-${change.id}` ? "Hide" : "Details"}</span>
              </button>
              {expanded === `${change.kind}-${change.id}` && <ChangeDetails change={change} />}
            </div>)}
          </div>
          {result.truncated && <Button variant="outline" size="sm" className="mt-3" disabled={loadingResult}
            onClick={() => setOffset(result.changes.length)}>
            {loadingResult && <Loader2 className="h-3 w-3 animate-spin" />} Load more changes
          </Button>}
        </>}
      </>}
    </CardContent>
  </Card>;
}
