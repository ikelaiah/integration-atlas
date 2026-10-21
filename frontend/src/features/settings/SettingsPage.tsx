import { useEffect, useState } from "react";
import { Database, Download, GraduationCap, HardDrive, Loader2, RotateCcw, Shield, Terminal } from "lucide-react";
import { api } from "@/lib/api";
import type { DemoReset, DemoStatus, Workspace } from "@/lib/types";
import { formatNumber } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Separator } from "@/components/ui/misc";

export function SettingsPage({
  workspaces,
  workspaceId,
  onSelectWorkspace,
  onReload,
  onDemoReset,
}: {
  workspaces: Workspace[];
  workspaceId: string | null;
  onSelectWorkspace: (id: string) => void;
  onReload: () => void;
  onDemoReset: (result: DemoReset) => void;
}) {
  const [version, setVersion] = useState("—");
  const hasDemo = workspaces.some((w) => w.is_demo);
  const [resetOpen, setResetOpen] = useState(false);

  useEffect(() => {
    api.health().then((h) => setVersion(h.version)).catch(() => setVersion("—"));
  }, []);

  return (
    <div className="h-full overflow-y-auto">
      <div className="mx-auto max-w-[860px] px-6 py-7">
        <h1 className="text-[21px] font-semibold leading-tight tracking-tight text-ink">
          Settings
        </h1>
        <p className="mt-1 text-[12px] leading-relaxed text-muted">
          Integration Atlas is local-first. Nothing leaves this machine.
        </p>

        <div className="mt-5 space-y-4">
          <Card>
            <CardHeader>
              <div className="flex items-center gap-1.5">
                <Database className="h-3.5 w-3.5 text-accent-strong" />
                <CardTitle>Workspaces</CardTitle>
              </div>
              <CardDescription>
                Each workspace keeps its own entities, relationships, scans and manual edits.
              </CardDescription>
            </CardHeader>
            <CardContent>
              <div className="space-y-1">
                {workspaces.map((workspace) => (
                  <button
                    key={workspace.id}
                    type="button"
                    onClick={() => onSelectWorkspace(workspace.id)}
                    className={`flex w-full items-center gap-2.5 rounded-[6px] border px-3 py-2 text-left transition-colors ${
                      workspace.id === workspaceId
                        ? "border-accent/40 bg-accent-soft"
                        : "border-line hover:bg-surface-2"
                    }`}
                  >
                    <div className="min-w-0 flex-1">
                      <div className="truncate text-[12px] text-ink">{workspace.name}</div>
                      <div className="truncate text-[10px] text-subtle">{workspace.slug}</div>
                    </div>
                    {workspace.is_demo && (
                      <Badge variant="accent" size="xs">
                        demo
                      </Badge>
                    )}
                    {workspace.id === workspaceId && (
                      <Badge variant="subtle" size="xs">
                        active
                      </Badge>
                    )}
                  </button>
                ))}
                {workspaces.length === 0 && (
                  <div className="rounded-[6px] border border-dashed border-line px-3 py-5 text-center text-[11.5px] text-subtle">
                    No workspaces yet.
                  </div>
                )}
              </div>
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <div className="flex items-center gap-1.5">
                <Shield className="h-3.5 w-3.5 text-success" />
                <CardTitle>Security model</CardTitle>
              </div>
            </CardHeader>
            <CardContent>
              <ul className="space-y-1.5 text-[11.5px] leading-relaxed text-muted">
                {[
                  "Local-first by default — the database lives on this machine.",
                  "No telemetry, no cloud upload, no external AI APIs.",
                  "Secrets are detected and redacted at the parser boundary, before persistence.",
                  "Redaction is over-eager by design: a false positive is cheaper than a leak.",
                  "Scans only read from paths you explicitly pass to the CLI or API.",
                  "Nothing in this application executes discovered artefacts.",
                ].map((line) => (
                  <li key={line} className="flex items-start gap-2">
                    <span className="mt-[6px] h-[4px] w-[4px] shrink-0 rounded-full bg-success/70" />
                    <span>{line}</span>
                  </li>
                ))}
              </ul>
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <div className="flex items-center gap-1.5">
                <Terminal className="h-3.5 w-3.5 text-subtle" />
                <CardTitle>CLI</CardTitle>
              </div>
            </CardHeader>
            <CardContent>
              <pre className="mono rounded-[6px] border border-line bg-canvas px-3 py-2.5 text-[10.5px] leading-relaxed text-ink-muted">
{`atlas init                   # create the local database
atlas demo                   # load or reset the Northstar demo
atlas scan run ./dir -w NAME # discover into your own workspace
atlas impact <name> -w NAME  # what breaks if this changes?
atlas serve                  # start the web application
atlas export -f json -w NAME`}
              </pre>
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <div className="flex items-center gap-1.5">
                <HardDrive className="h-3.5 w-3.5 text-subtle" />
                <CardTitle>About</CardTitle>
              </div>
            </CardHeader>
            <CardContent>
              <div className="flex items-center gap-2 text-[11.5px] text-muted">
                <span className="text-ink">Integration Atlas</span>
                <span className="text-line-strong">·</span>
                <span className="mono">v{version}</span>
                <span className="text-line-strong">·</span>
                <span>Apache-2.0</span>
              </div>
              <Separator className="my-3" />
              <div className="flex items-center gap-2">
                <Button variant="outline" size="sm" onClick={onReload}>
                  <Download className="h-3 w-3" /> Reload data
                </Button>
                <Button variant="outline" size="sm" onClick={() => setResetOpen(true)}>
                  {hasDemo ? (
                    <>
                      <RotateCcw className="h-3 w-3" /> Reset demo estate
                    </>
                  ) : (
                    <>
                      <GraduationCap className="h-3 w-3" /> Load demo estate
                    </>
                  )}
                </Button>
              </div>
            </CardContent>
          </Card>
        </div>
      </div>
      <DemoResetDialog
        open={resetOpen}
        onOpenChange={setResetOpen}
        onDone={(result) => {
          setResetOpen(false);
          onDemoReset(result);
        }}
      />
    </div>
  );
}

function plural(count: number, one: string, many = `${one}s`): string {
  return `${formatNumber(count)} ${count === 1 ? one : many}`;
}

/** Says exactly what a reset restores and what it keeps before anything changes. */
function DemoResetDialog({
  open,
  onOpenChange,
  onDone,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onDone: (result: DemoReset) => void;
}) {
  const [status, setStatus] = useState<DemoStatus | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [working, setWorking] = useState(false);

  useEffect(() => {
    if (!open) return;
    setStatus(null);
    setError(null);
    api.demo.status().then(setStatus).catch((err: Error) => setError(err.message));
  }, [open]);

  const confirm = () => {
    setWorking(true);
    setError(null);
    api.demo
      .reset()
      .then(onDone)
      .catch((err: Error) => setError(err.message))
      .finally(() => setWorking(false));
  };

  const exists = Boolean(status?.workspace);
  const otherParts = status
    ? [
        status.scans ? plural(status.scans, "scan") : null,
        status.other_entities ? plural(status.other_entities, "entity", "entities") : null,
        status.other_relationships ? plural(status.other_relationships, "relationship") : null,
      ].filter(Boolean)
    : [];

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{exists || !status ? "Reset the Northstar demo?" : "Load the Northstar demo?"}</DialogTitle>
          <DialogDescription>
            {!status && !error && "Checking the demo workspace…"}
            {status && !exists &&
              `Creates a separate demo workspace with ${plural(status.demo_entities, "entity", "entities")} and ${plural(status.demo_relationships, "relationship")}. Your workspaces are not changed.`}
            {status && exists &&
              `Restores ${plural(status.demo_entities, "entity", "entities")} and ${plural(status.demo_relationships, "relationship")} to the original demo data. Other workspaces are not changed.`}
          </DialogDescription>
        </DialogHeader>
        <div className="space-y-2 px-5 text-[12px] leading-relaxed text-muted">
          {status && exists && (status.edited_entities > 0 || status.reviewed_relationships > 0) && (
            <p>
              Reverts {plural(status.edited_entities, "entity edit")} and{" "}
              {plural(status.reviewed_relationships, "review decision")} made in the demo.
            </p>
          )}
          {status?.has_other_data && (
            <div className="rounded-[6px] border border-accent/30 bg-accent-soft px-3 py-2 text-ink">
              The demo workspace also holds data that is not part of the demo:{" "}
              {otherParts.join(", ")}. Nothing is deleted. Atlas keeps that workspace, with its scan
              history, as <span className="font-medium">“{status.kept_workspace_name}”</span> and
              creates a fresh demo workspace.
            </div>
          )}
          {error && (
            <div className="rounded-[5px] border border-danger/30 bg-danger/10 px-2.5 py-1.5 text-[11px] text-danger">
              {error}
            </div>
          )}
        </div>
        <DialogFooter>
          <Button variant="outline" size="sm" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button size="sm" onClick={confirm} disabled={!status || working}>
            {working && <Loader2 className="h-3.5 w-3.5 animate-spin" />}
            {exists ? "Reset demo" : "Load demo"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
