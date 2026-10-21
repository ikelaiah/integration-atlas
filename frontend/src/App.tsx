import { useCallback, useEffect, useMemo, useState, type ReactNode } from "react";
import { Navigate, Route, Routes, useNavigate } from "react-router-dom";
import { api } from "@/lib/api";
import { pickWorkspace, readStoredWorkspace, storeWorkspace } from "@/lib/workspace-choice";
import type { EntityType, RiskFinding, ScanProgress, Workspace } from "@/lib/types";
import { Sidebar } from "@/components/layout/Sidebar";
import { TopBar } from "@/components/layout/TopBar";
import { CommandPalette } from "@/components/layout/CommandPalette";
import { OverviewPage } from "@/features/overview/OverviewPage";
import { AtlasPage } from "@/features/atlas/AtlasPage";
import { EntityListPage } from "@/features/entities/EntityListPage";
import { RisksPage } from "@/features/risks/RisksPage";
import { ScansPage } from "@/features/scans/ScansPage";
import { ReviewPage } from "@/features/review/ReviewPage";
import { SettingsPage } from "@/features/settings/SettingsPage";
import { FirstRunPage, StartupError } from "@/features/onboarding/FirstRunPage";
import { TooltipProvider } from "@/components/ui/tooltip";
import { X } from "lucide-react";

const SYSTEM_TYPES: EntityType[] = ["system", "application", "external_service", "server"];
const INTEGRATION_TYPES: EntityType[] = [
  "integration",
  "script",
  "scheduled_job",
  "api",
  "endpoint",
  "queue",
  "sftp_location",
];
const DATA_TYPES: EntityType[] = [
  "database",
  "schema",
  "table",
  "column",
  "file",
  "directory",
  "sftp_location",
];

type BootState = { kind: "loading" } | { kind: "ready" } | { kind: "error"; message: string };

export default function App() {
  const [boot, setBoot] = useState<BootState>({ kind: "loading" });
  const [workspaces, setWorkspaces] = useState<Workspace[]>([]);
  const [workspaceId, setWorkspaceId] = useState<string | null>(null);
  const [risks, setRisks] = useState<RiskFinding[]>([]);
  const [risksLoading, setRisksLoading] = useState(true);
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);
  const [paletteOpen, setPaletteOpen] = useState(false);
  const [selectedName, setSelectedName] = useState<string | null>(null);
  // Survive the remount that follows a switch to the workspace a scan created.
  const [recentScan, setRecentScan] = useState<ScanProgress | null>(null);
  const [dataVersion, setDataVersion] = useState(0);
  const [notice, setNotice] = useState<string | null>(null);
  const navigate = useNavigate();

  // ------------------------------------------------------------------ //
  // bootstrap
  // ------------------------------------------------------------------ //
  // An empty database stays empty until the person chooses the demo or a scan.
  const bootstrap = useCallback(async (preferred?: string) => {
    try {
      const list = await api.workspaces.list();
      setWorkspaces(list);
      setWorkspaceId((current) => pickWorkspace(list, preferred ?? current ?? readStoredWorkspace()));
      setBoot({ kind: "ready" });
    } catch (err) {
      setBoot({ kind: "error", message: err instanceof Error ? err.message : String(err) });
    }
  }, []);

  useEffect(() => {
    bootstrap();
  }, [bootstrap]);

  useEffect(() => {
    if (boot.kind === "ready") storeWorkspace(workspaceId);
  }, [boot.kind, workspaceId]);

  const selectWorkspace = useCallback((id: string) => {
    setSelectedName(null);
    setRecentScan(null);
    setNotice(null);
    setWorkspaceId(id);
  }, []);

  useEffect(() => {
    setRisks([]);
    if (!workspaceId) return;
    let cancelled = false;
    setRisksLoading(true);
    // Risk findings are generated during seeding/scanning; this just reads them.
    api
      .risks(workspaceId)
      .then((summary) => {
        if (!cancelled) setRisks(summary.findings);
      })
      .catch(() => {
        if (!cancelled) setRisks([]);
      })
      .finally(() => {
        if (!cancelled) setRisksLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [workspaceId, dataVersion]);

  // ------------------------------------------------------------------ //
  // global shortcuts
  // ------------------------------------------------------------------ //
  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      const target = event.target as HTMLElement | null;
      const typing =
        target &&
        (target.tagName === "INPUT" ||
          target.tagName === "TEXTAREA" ||
          target.isContentEditable);

      if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "k") {
        event.preventDefault();
        setPaletteOpen((v) => !v);
        return;
      }
      if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "b") {
        event.preventDefault();
        setSidebarCollapsed((v) => !v);
        return;
      }
      if (event.key === "/" && !typing) {
        event.preventDefault();
        setPaletteOpen(true);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  const workspaceName = useMemo(
    () => workspaces.find((w) => w.id === workspaceId)?.name ?? "None yet",
    [workspaces, workspaceId],
  );
  const isDemo = useMemo(
    () => workspaces.find((w) => w.id === workspaceId)?.is_demo ?? false,
    [workspaces, workspaceId],
  );

  const handleSelectEntity = useCallback(
    (id: string) => {
      setSelectedName(null);
      navigate("/atlas");
      // Atlas reads selection via a custom event so we don't need route params.
      window.dispatchEvent(new CustomEvent("atlas:select", { detail: id }));
    },
    [navigate],
  );

  if (boot.kind === "loading") {
    return (
      <div className="flex h-screen w-screen items-center justify-center bg-canvas text-[12px] text-subtle">
        Loading Atlas…
      </div>
    );
  }
  if (boot.kind === "error") {
    return <StartupError message={boot.message} onRetry={() => bootstrap()} />;
  }

  // Pages that show one workspace's data need a workspace; offer the first-run choice instead.
  const needsWorkspace = (page: ReactNode) =>
    workspaceId ? page : <FirstRunPage onDemoLoaded={(id) => bootstrap(id)} />;

  return (
    <TooltipProvider delayDuration={120}>
      <div className="flex h-screen w-screen overflow-hidden bg-canvas text-ink">
        <Sidebar
          collapsed={sidebarCollapsed}
          onToggle={() => setSidebarCollapsed((v) => !v)}
          workspaceName={workspaceName}
          isDemo={isDemo}
          workspaces={workspaces}
          workspaceId={workspaceId}
          onSelectWorkspace={selectWorkspace}
        />

        <div className="flex min-w-0 flex-1 flex-col">
          <TopBar
            onOpenPalette={() => setPaletteOpen(true)}
            onOpenPathFinder={() => {
              navigate("/atlas");
              window.dispatchEvent(new CustomEvent("atlas:open-path-finder"));
            }}
            onOpenImpact={() => {
              navigate("/atlas");
              window.dispatchEvent(new CustomEvent("atlas:open-impact"));
            }}
            selectedName={selectedName}
          />

          {/* Remount pages on a workspace switch so no selection, impact, path or
              preview from the previous workspace survives. */}
          {notice && (
            <div role="status" className="flex items-center gap-2 border-b border-accent/30 bg-accent-soft px-4 py-2 text-[11.5px] text-ink">
              <span className="flex-1">{notice}</span>
              <button type="button" onClick={() => setNotice(null)} aria-label="Dismiss notice" className="rounded-[4px] p-1 text-subtle hover:bg-surface-2 hover:text-ink">
                <X className="h-3 w-3" />
              </button>
            </div>
          )}
          <main key={workspaceId ?? "none"} className="min-h-0 flex-1">
            <Routes>
              <Route path="/" element={needsWorkspace(<OverviewPage workspaceId={workspaceId} />)} />
              <Route
                path="/atlas"
                element={needsWorkspace(<AtlasPage workspaceId={workspaceId} risks={risks} />)}
              />
              <Route
                path="/systems"
                element={needsWorkspace(
                  <EntityListPage
                    workspaceId={workspaceId}
                    title="Systems & infrastructure"
                    description="Business systems, applications, external services and the servers they run on."
                    types={SYSTEM_TYPES}
                    risks={risks}
                    onSelect={handleSelectEntity}
                  />
                )}
              />
              <Route
                path="/integrations"
                element={needsWorkspace(
                  <EntityListPage
                    workspaceId={workspaceId}
                    title="Integrations"
                    description="Named flows, scripts, scheduled jobs, APIs and file exchanges that move data between systems."
                    types={INTEGRATION_TYPES}
                    risks={risks}
                    onSelect={handleSelectEntity}
                  />
                )}
              />
              <Route
                path="/data"
                element={needsWorkspace(
                  <EntityListPage
                    workspaceId={workspaceId}
                    title="Data"
                    description="Databases, schemas, tables, columns and the files that carry them between systems."
                    types={DATA_TYPES}
                    risks={risks}
                    onSelect={handleSelectEntity}
                  />
                )}
              />
              <Route
                path="/risks"
                element={needsWorkspace(
                  <RisksPage
                    risks={risks}
                    loading={risksLoading}
                    onSelect={(id) => {
                      handleSelectEntity(id);
                    }}
                  />
                )}
              />
              <Route
                path="/scans"
                element={
                  <ScansPage
                    workspaces={workspaces}
                    workspaceId={workspaceId}
                    recentScan={recentScan}
                    onScanComplete={(result) => {
                      setRecentScan(result);
                      setDataVersion((v) => v + 1);
                      bootstrap(result.scan.workspace_id);
                    }}
                  />
                }
              />
              <Route path="/review" element={needsWorkspace(<ReviewPage workspaceId={workspaceId} />)} />
              <Route
                path="/settings"
                element={
                  <SettingsPage
                    workspaces={workspaces}
                    workspaceId={workspaceId}
                    onSelectWorkspace={selectWorkspace}
                    onReload={() => bootstrap()}
                    onDemoReset={(result) => {
                      setRecentScan(null);
                      setDataVersion((v) => v + 1);
                      setNotice(
                        result.kept_workspace_name
                          ? `The demo was reset. Scan results and other data found in it are kept in the workspace “${result.kept_workspace_name}”.`
                          : "The Northstar demo is loaded with its original data.",
                      );
                      bootstrap(result.workspace_id);
                    }}
                  />
                }
              />
              <Route path="*" element={<Navigate to="/" replace />} />
            </Routes>
          </main>
        </div>

        <CommandPalette
          open={paletteOpen}
          onClose={() => setPaletteOpen(false)}
          workspaceId={workspaceId}
          onSelectEntity={handleSelectEntity}
          onImpact={(id) => {
            navigate("/atlas");
            window.dispatchEvent(new CustomEvent("atlas:impact", { detail: id }));
            setPaletteOpen(false);
          }}
        />
      </div>
    </TooltipProvider>
  );
}
