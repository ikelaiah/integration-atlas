import { useCallback, useEffect, useMemo, useState } from "react";
import { Navigate, Route, Routes, useNavigate } from "react-router-dom";
import { api } from "@/lib/api";
import type { EntityType, RiskFinding, Workspace } from "@/lib/types";
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
import { TooltipProvider } from "@/components/ui/tooltip";

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

export default function App() {
  const [workspaces, setWorkspaces] = useState<Workspace[]>([]);
  const [workspaceId, setWorkspaceId] = useState<string | null>(null);
  const [risks, setRisks] = useState<RiskFinding[]>([]);
  const [risksLoading, setRisksLoading] = useState(true);
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);
  const [paletteOpen, setPaletteOpen] = useState(false);
  const [selectedName, setSelectedName] = useState<string | null>(null);
  const navigate = useNavigate();

  // ------------------------------------------------------------------ //
  // bootstrap
  // ------------------------------------------------------------------ //
  const bootstrap = useCallback(async () => {
    try {
      let list = await api.workspaces.list();
      if (list.length === 0) {
        await api.workspaces.seedDemo();
        list = await api.workspaces.list();
      }
      setWorkspaces(list);
      setWorkspaceId((current) => current ?? list[0]?.id ?? null);
    } catch {
      setWorkspaces([]);
    }
  }, []);

  useEffect(() => {
    bootstrap();
  }, [bootstrap]);

  useEffect(() => {
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
  }, [workspaceId]);

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
    () => workspaces.find((w) => w.id === workspaceId)?.name ?? "—",
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

  return (
    <TooltipProvider delayDuration={120}>
      <div className="flex h-screen w-screen overflow-hidden bg-canvas text-ink">
        <Sidebar
          collapsed={sidebarCollapsed}
          onToggle={() => setSidebarCollapsed((v) => !v)}
          workspaceName={workspaceName}
          isDemo={isDemo}
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

          <main className="min-h-0 flex-1">
            <Routes>
              <Route path="/" element={<OverviewPage workspaceId={workspaceId} />} />
              <Route
                path="/atlas"
                element={<AtlasPage workspaceId={workspaceId} risks={risks} />}
              />
              <Route
                path="/systems"
                element={
                  <EntityListPage
                    workspaceId={workspaceId}
                    title="Systems & infrastructure"
                    description="Business systems, applications, external services and the servers they run on."
                    types={SYSTEM_TYPES}
                    risks={risks}
                    onSelect={handleSelectEntity}
                  />
                }
              />
              <Route
                path="/integrations"
                element={
                  <EntityListPage
                    workspaceId={workspaceId}
                    title="Integrations"
                    description="Named flows, scripts, scheduled jobs, APIs and file exchanges that move data between systems."
                    types={INTEGRATION_TYPES}
                    risks={risks}
                    onSelect={handleSelectEntity}
                  />
                }
              />
              <Route
                path="/data"
                element={
                  <EntityListPage
                    workspaceId={workspaceId}
                    title="Data"
                    description="Databases, schemas, tables, columns and the files that carry them between systems."
                    types={DATA_TYPES}
                    risks={risks}
                    onSelect={handleSelectEntity}
                  />
                }
              />
              <Route
                path="/risks"
                element={
                  <RisksPage
                    risks={risks}
                    loading={risksLoading}
                    onSelect={(id) => {
                      handleSelectEntity(id);
                    }}
                  />
                }
              />
              <Route
                path="/scans"
                element={
                  <ScansPage
                    workspaceId={workspaceId}
                    onScanComplete={() => {
                      bootstrap();
                      if (workspaceId) api.risks(workspaceId).then((result) => setRisks(result.findings));
                    }}
                  />
                }
              />
              <Route path="/review" element={<ReviewPage workspaceId={workspaceId} />} />
              <Route
                path="/settings"
                element={
                  <SettingsPage
                    workspaces={workspaces}
                    workspaceId={workspaceId}
                    onSelectWorkspace={setWorkspaceId}
                    onReload={bootstrap}
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
