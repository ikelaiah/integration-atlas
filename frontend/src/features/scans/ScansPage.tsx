import { useEffect, useState } from "react";
import {
  CheckCircle2,
  FileSearch,
  FolderSearch2,
  Loader2,
  Play,
  RefreshCw,
  ScanSearch,
  ShieldOff,
} from "lucide-react";
import { api } from "@/lib/api";
import { HistoryCompare } from "@/components/panels/HistoryCompare";
import type { ScanDiff, ScanPreview, ScanProgress, Workspace } from "@/lib/types";
import { cn, formatNumber, relativeTime } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Input, Label } from "@/components/ui/input";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { EmptyState, Stat, Skeleton } from "@/components/ui/misc";

const NEW_WORKSPACE = "__new__";

export function ScansPage({
  workspaces,
  workspaceId,
  recentScan,
  onScanComplete,
}: {
  workspaces: Workspace[];
  workspaceId: string | null;
  /** The scan just applied, kept across the switch to the workspace it wrote to. */
  recentScan: ScanProgress | null;
  onScanComplete: (result: ScanProgress) => void;
}) {
  const recent = recentScan?.scan.workspace_id === workspaceId ? recentScan : null;
  const ownWorkspaces = workspaces.filter((w) => !w.is_demo);
  const active = workspaces.find((w) => w.id === workspaceId) ?? null;
  const [scans, setScans] = useState<ScanProgress[]>([]);
  const [loading, setLoading] = useState(true);
  const [rootPath, setRootPath] = useState("");
  // Scans never target the demo; while it is active, default to a new workspace.
  const [target, setTarget] = useState(active && !active.is_demo ? active.id : NEW_WORKSPACE);
  const [newName, setNewName] = useState("");
  const [running, setRunning] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [lastResult, setLastResult] = useState<ScanProgress | null>(recent);
  const [preview, setPreview] = useState<ScanPreview | null>(null);
  const [previewKey, setPreviewKey] = useState("");
  const [previewPath, setPreviewPath] = useState("");
  const [selectedScan, setSelectedScan] = useState<string | null>(recent?.scan.id ?? null);
  // A preview stays valid only for the folder and destination it was made for.
  const currentKey = `${rootPath.trim()}|${target}|${newName.trim()}`;

  const load = () => {
    if (!workspaceId) {
      setScans([]);
      setLoading(false);
      return;
    }
    setLoading(true);
    api.scans
      .list(workspaceId)
      .then(setScans)
      .catch((err: Error) => { setScans([]); setError(err.message); })
      .finally(() => setLoading(false));
  };

  useEffect(load, [workspaceId]);

  const previewScan = () => {
    if (!rootPath.trim()) return;
    const key = currentKey;
    setRunning(true);
    setError(null);
    setPreview(null);
    setLastResult(null);
    const destination = target === NEW_WORKSPACE
      ? { workspace_name: newName.trim() || undefined }
      : { workspace_id: target };
    api.scans.preview({ root_path: rootPath.trim(), ...destination })
      .then((result) => { setPreview(result); setPreviewPath(rootPath.trim()); setPreviewKey(key); })
      .catch((err: Error) => setError(err.message))
      .finally(() => setRunning(false));
  };

  const runScan = () => {
    if (!preview) return;
    setRunning(true);
    setError(null);
    // Apply to the workspace the preview resolved; a blank name became the folder name.
    const destination = target === NEW_WORKSPACE
      ? { workspace_name: preview.workspace_name }
      : { workspace_id: target };
    api.scans
      .run({ root_path: previewPath, ...destination })
      .then((result) => {
        setLastResult(result);
        setPreview(null);
        setSelectedScan(result.scan.id);
        load();
        onScanComplete(result);
      })
      .catch((err: Error) => setError(err.message))
      .finally(() => setRunning(false));
  };

  return (
    <div className="h-full overflow-y-auto">
      <div className="mx-auto max-w-[1180px] px-6 py-7">
        <div>
          <h1 className="text-[21px] font-semibold leading-tight tracking-tight text-ink">
            Discovery scans
          </h1>
          <p className="mt-1 max-w-[680px] text-[12px] leading-relaxed text-muted">
            Point Atlas at a folder of scripts, SQL, config and scheduler exports. Secrets are
            redacted before anything reaches the database.
          </p>
        </div>

        <Card className="mt-5">
          <CardHeader>
            <div className="flex items-center gap-1.5">
              <FolderSearch2 className="h-3.5 w-3.5 text-accent-strong" />
              <CardTitle>New scan</CardTitle>
            </div>
          </CardHeader>
          <CardContent>
            <div className="flex flex-wrap items-end gap-2.5">
              <div className="flex-1">
                <Label htmlFor="scan-root-path">Folder path</Label>
                <Input
                  id="scan-root-path"
                  value={rootPath}
                  onChange={(e) => setRootPath(e.target.value)}
                  placeholder="/path/to/integrations  (e.g. ./examples/northstar)"
                  className="mt-1"
                  onKeyDown={(e) => e.key === "Enter" && previewScan()}
                />
              </div>
              <Button variant="default" size="md" onClick={previewScan} disabled={!rootPath.trim() || running}>
                {running ? (
                  <>
                    <Loader2 className="h-3.5 w-3.5 animate-spin" /> Scanning…
                  </>
                ) : (
                  <>
                    <FileSearch className="h-3.5 w-3.5" /> Preview scan
                  </>
                )}
              </Button>
            </div>
            <div className="mt-3 flex flex-wrap items-end gap-2.5">
              <div className="w-full sm:w-[280px]">
                <Label htmlFor="scan-target">Scan into</Label>
                <select
                  id="scan-target"
                  value={target}
                  onChange={(e) => setTarget(e.target.value)}
                  className="mt-1 h-8 w-full rounded-[5px] border border-line-strong bg-surface-2 px-2 text-[12.5px] text-ink focus:border-accent focus:outline-none focus:ring-1 focus:ring-accent/40"
                >
                  {ownWorkspaces.map((w) => (
                    <option key={w.id} value={w.id}>{w.name}</option>
                  ))}
                  <option value={NEW_WORKSPACE}>New workspace…</option>
                </select>
              </div>
              {target === NEW_WORKSPACE && (
                <div className="min-w-[220px] flex-1">
                  <Label htmlFor="scan-new-workspace">New workspace name</Label>
                  <Input
                    id="scan-new-workspace"
                    value={newName}
                    onChange={(e) => setNewName(e.target.value)}
                    placeholder="Defaults to the folder name"
                    className="mt-1"
                    onKeyDown={(e) => e.key === "Enter" && previewScan()}
                  />
                </div>
              )}
            </div>
            {active?.is_demo && (
              <p className="mt-2 text-[11px] text-muted">
                {active.name} is the demo workspace and keeps only its sample data, so scans go
                into a workspace of your own.
              </p>
            )}
            {preview && currentKey === previewKey && (
              <div className="mt-3 rounded-[7px] border border-accent/30 bg-surface-2 p-3">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <div>
                    <div className="text-[12px] font-semibold text-ink">Proposed changes</div>
                    <p className="mt-0.5 text-[11px] text-muted">
                      Into <span className="text-ink">{preview.workspace_name}</span>
                      {preview.creates_workspace ? ", a new workspace created when you apply" : ""}.
                      Preview changes nothing; Apply scans the current files again.
                    </p>
                  </div>
                  <Button size="sm" onClick={runScan} disabled={running}>
                    <Play className="h-3.5 w-3.5" /> Apply scan
                  </Button>
                </div>
                <DiffSummary diff={preview.diff_summary} />
              </div>
            )}
            {error && (
              <div className="mt-2 rounded-[5px] border border-danger/30 bg-danger/10 px-2.5 py-1.5 text-[11px] text-danger">
                {error}
              </div>
            )}
            {lastResult && !error && (
              <div className="mt-3 rounded-[7px] border border-line bg-surface-2 p-3">
                <div className="flex items-center gap-1.5">
                  <CheckCircle2 className="h-3.5 w-3.5 text-success" />
                  <span className="text-[12px] font-medium text-ink">Scan complete</span>
                  <Badge variant="subtle" size="xs">
                    {lastResult.scan.status}
                  </Badge>
                </div>
                <div className="mt-2.5 grid grid-cols-2 gap-2 md:grid-cols-4">
                  <Stat label="Files" value={formatNumber(lastResult.files_discovered)} />
                  <Stat label="Entities" value={formatNumber(lastResult.entities)} />
                  <Stat label="Relationships" value={formatNumber(lastResult.relationships)} />
                  <Stat
                    label="Secrets redacted"
                    value={formatNumber(lastResult.secrets_redacted)}
                    accent="#f87171"
                  />
                </div>
                {Object.keys(lastResult.by_extension).length > 0 && (
                  <div className="mt-2.5 flex flex-wrap gap-1.5">
                    {Object.entries(lastResult.by_extension).map(([ext, count]) => (
                      <Badge key={ext} variant="subtle" size="xs">
                        {ext} <span className="tabular opacity-70">{count}</span>
                      </Badge>
                    ))}
                  </div>
                )}
                {hasScanDiff(lastResult.scan.diff_summary) && (
                  <DiffSummary diff={lastResult.scan.diff_summary} />
                )}
              </div>
            )}
          </CardContent>
        </Card>

        {!loading && workspaceId && <HistoryCompare workspaceId={workspaceId} scans={scans} />}

        <div className="mt-6">
          <div className="flex items-center gap-2">
            <h2 className="text-[13px] font-semibold text-ink">
              Scan history
              {active && <span className="font-normal text-muted"> · {active.name}</span>}
            </h2>
            <Button variant="ghost" size="xs" onClick={load}>
              <RefreshCw className="h-3 w-3" /> Refresh
            </Button>
          </div>

          <div className="mt-2.5 space-y-2">
            {loading && <Skeleton className="h-[62px]" />}
            {!loading && scans.length === 0 && (
              <EmptyState
                icon={<ScanSearch className="h-5 w-5" />}
                title="No scans yet"
                description="Run a scan above to discover integrations from a folder of artefacts."
              />
            )}
            {!loading &&
              scans.map((scan) => (
                <button type="button" onClick={() => setSelectedScan(selectedScan === scan.scan.id ? null : scan.scan.id)}
                  aria-expanded={selectedScan === scan.scan.id}
                  key={scan.scan.id}
                  className="flex w-full flex-wrap items-center gap-3 rounded-[8px] border border-line bg-surface px-3.5 py-2.5 text-left hover:bg-surface-2"
                >
                  <div
                    className={cn(
                      "flex h-7 w-7 items-center justify-center rounded-full",
                      scan.scan.status === "completed" ? "bg-success/12 text-success" : "bg-surface-2 text-subtle",
                    )}
                  >
                    {scan.scan.status === "completed" ? (
                      <CheckCircle2 className="h-3.5 w-3.5" />
                    ) : scan.scan.status === "failed" ? (
                      <ShieldOff className="h-3.5 w-3.5" />
                    ) : (
                      <FileSearch className="h-3.5 w-3.5" />
                    )}
                  </div>
                  <div className="min-w-0 flex-1">
                    <div className="truncate text-[12px] text-ink">{scan.scan.root_path}</div>
                    <div className="text-[10px] text-subtle">
                      {relativeTime(scan.scan.started_at)} · {scan.scan.status}
                    </div>
                  </div>
                  <div className="flex items-center gap-3 text-[10.5px] text-muted">
                    <span className="tabular">{formatNumber(scan.files_discovered)} files</span>
                    <span className="tabular">{formatNumber(scan.entities)} entities</span>
                    <span className="tabular">{formatNumber(scan.relationships)} rels</span>
                    {scan.secrets_redacted > 0 && (
                      <Badge variant="danger" size="xs">
                        {scan.secrets_redacted} redacted
                      </Badge>
                    )}
                  </div>
                  {selectedScan === scan.scan.id && hasScanDiff(scan.scan.diff_summary) && (
                    <div className="w-full"><DiffSummary diff={scan.scan.diff_summary} /></div>
                  )}
                </button>
              ))}
          </div>
        </div>
      </div>
    </div>
  );
}

function hasScanDiff(value: unknown): value is ScanDiff {
  return typeof value === "object" && value !== null && "total" in value && "changes" in value;
}

function DiffSummary({ diff }: { diff: ScanDiff }) {
  return <div className="mt-2.5">
    <div className="flex flex-wrap gap-x-4 gap-y-1 text-[11px] text-muted">
      {(["entities", "relationships"] as const).map((kind) =>
        <span key={kind}><span className="font-medium text-ink">{kind}</span> · {diff[kind].added} added · {diff[kind].updated} updated · {diff[kind].removed} retired</span>
      )}
    </div>
    {diff.changes.length > 0 ? <ul className="mt-2 max-h-48 space-y-1 overflow-y-auto border-t border-line pt-2 text-[11px]">
      {diff.changes.map((change) => <li key={`${change.kind}-${change.id}`} className="flex gap-2">
        <span className={cn("w-14 shrink-0 capitalize", change.action === "removed" ? "text-danger" : "text-accent-strong")}>{change.action}</span>
        <span className="truncate text-ink" title={change.name}>{change.name}</span>
        <span className="ml-auto shrink-0 text-subtle">{change.type.replaceAll("_", " ")}</span>
      </li>)}
      {diff.truncated && <li className="text-subtle">More changes omitted from this list.</li>}
    </ul> : <p className="mt-2 text-[11px] text-subtle">No graph changes.</p>}
  </div>;
}
