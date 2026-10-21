import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { AlertTriangle, FolderSearch2, GraduationCap, Loader2, RefreshCw } from "lucide-react";
import { api } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";

/** Shown while the database has no workspace: nothing is loaded until a choice is made. */
export function FirstRunPage({ onDemoLoaded }: { onDemoLoaded: (workspaceId: string) => void }) {
  const navigate = useNavigate();
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const loadDemo = () => {
    setLoading(true);
    setError(null);
    api.demo
      .reset()
      .then((result) => onDemoLoaded(result.workspace_id))
      .catch((err: Error) => setError(err.message))
      .finally(() => setLoading(false));
  };

  return (
    <div className="h-full overflow-y-auto">
      <div className="mx-auto max-w-[860px] px-6 py-10">
        <h1 className="text-[24px] font-semibold leading-tight tracking-tight text-ink">
          Welcome to Integration Atlas
        </h1>
        <p className="mt-1.5 max-w-[620px] text-[12.5px] leading-relaxed text-muted">
          Atlas has no workspace yet. Explore the sample estate first, or map your own files.
          Each workspace keeps its own entities, scans and edits, so the demo never mixes with your
          estate.
        </p>

        <div className="mt-6 grid grid-cols-1 gap-4 md:grid-cols-2">
          <Card>
            <CardHeader>
              <div className="flex items-center gap-1.5">
                <GraduationCap className="h-3.5 w-3.5 text-accent-strong" />
                <CardTitle>Explore the Northstar demo</CardTitle>
              </div>
              <CardDescription>
                A fictional education group with a legacy student system, file drops and SaaS
                integrations. It loads into its own demo workspace.
              </CardDescription>
            </CardHeader>
            <CardContent>
              <Button size="sm" onClick={loadDemo} disabled={loading}>
                {loading ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : null}
                Load the demo
              </Button>
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <div className="flex items-center gap-1.5">
                <FolderSearch2 className="h-3.5 w-3.5 text-accent-strong" />
                <CardTitle>Scan your own folder</CardTitle>
              </div>
              <CardDescription>
                Point Atlas at scripts, SQL, config and scheduler exports on this machine. Files are
                read, never run, and nothing is uploaded.
              </CardDescription>
            </CardHeader>
            <CardContent>
              <Button variant="outline" size="sm" onClick={() => navigate("/scans")}>
                Choose a folder
              </Button>
            </CardContent>
          </Card>
        </div>

        {error && (
          <div className="mt-4 rounded-[5px] border border-danger/30 bg-danger/10 px-2.5 py-1.5 text-[11px] text-danger">
            The demo could not be loaded: {error}
          </div>
        )}
      </div>
    </div>
  );
}

/** Replaces the app when the local API cannot be reached on startup. */
export function StartupError({ message, onRetry }: { message: string; onRetry: () => void }) {
  return (
    <div className="flex h-screen w-screen items-center justify-center bg-canvas p-6 text-ink">
      <div role="alert" className="w-full max-w-[460px] rounded-[10px] border border-line bg-surface p-5">
        <div className="flex items-center gap-2">
          <AlertTriangle className="h-4 w-4 text-danger" />
          <h1 className="text-[14px] font-semibold">Atlas could not reach its local API</h1>
        </div>
        <p className="mt-2 text-[12px] leading-relaxed text-muted">
          The web app loads data from the Atlas server on this machine. Start it with{" "}
          <code className="mono rounded-[4px] bg-surface-2 px-1 py-0.5 text-[11px] text-ink">atlas serve</code>
          , then try again. During frontend development, keep the server running on port 8000.
        </p>
        <p className="mono mt-2 break-words text-[10.5px] text-subtle">{message}</p>
        <Button className="mt-4" size="sm" onClick={onRetry}>
          <RefreshCw className="h-3.5 w-3.5" /> Retry
        </Button>
      </div>
    </div>
  );
}
