import { useEffect, useState } from "react";
import { Database, Download, HardDrive, Shield, Terminal, Trash2 } from "lucide-react";
import { api } from "@/lib/api";
import type { Workspace } from "@/lib/types";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Separator } from "@/components/ui/misc";

export function SettingsPage({
  workspaces,
  workspaceId,
  onSelectWorkspace,
  onReload,
}: {
  workspaces: Workspace[];
  workspaceId: string | null;
  onSelectWorkspace: (id: string) => void;
  onReload: () => void;
}) {
  const [version, setVersion] = useState("—");

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
{`atlas init          # create the local database
atlas demo          # load the Northstar demo estate
atlas scan ./dir    # discover integrations from artefacts
atlas impact <name> # what breaks if this changes?
atlas serve         # start the web application
atlas export -f json`}
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
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => api.workspaces.seedDemo().then(onReload)}
                >
                  <Trash2 className="h-3 w-3" /> Reset demo estate
                </Button>
              </div>
            </CardContent>
          </Card>
        </div>
      </div>
    </div>
  );
}
