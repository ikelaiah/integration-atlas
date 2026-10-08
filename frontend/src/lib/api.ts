/** Thin typed client for the Integration Atlas API. */

import type {
  EntityDetail,
  GraphResponse,
  Impact,
  Overview,
  PathResult,
  RelationshipDetail,
  RiskFinding,
  ScanProgress,
  SearchResponse,
  Traversal,
  Workspace,
} from "./types";

const BASE = "";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${BASE}${path}`, {
    headers: { Accept: "application/json", ...(init?.headers ?? {}) },
    ...init,
  });
  if (!response.ok) {
    let detail = response.statusText;
    try {
      const body = await response.json();
      detail = body.detail ?? detail;
    } catch {
      /* non-JSON error body */
    }
    throw new Error(`${response.status}: ${detail}`);
  }
  return (await response.json()) as T;
}

function qs(params: Record<string, unknown>): string {
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value === undefined || value === null || value === "") continue;
    if (Array.isArray(value)) {
      for (const item of value) search.append(key, String(item));
    } else {
      search.set(key, String(value));
    }
  }
  const s = search.toString();
  return s ? `?${s}` : "";
}

export const api = {
  health: () => request<{ status: string; version: string }>("/api/health"),

  workspaces: {
    list: () => request<Workspace[]>("/api/workspaces"),
    overview: (id: string) => request<Overview>(`/api/workspaces/${id}/overview`),
    seedDemo: (id = "demo") =>
      request<{ status: string; entities_added: number; relationships_added: number }>(
        `/api/workspaces/${id}/seed-demo`,
        { method: "POST" },
      ),
  },

  graph: (workspaceId: string, params: { entity_type?: string[]; min_confidence?: string; environment?: string[]; limit?: number } = {}) =>
    request<GraphResponse>(`/api/graph${qs({ workspace_id: workspaceId, ...params })}`),

  entity: (id: string) => request<EntityDetail>(`/api/entities/${id}`),

  entityRelationships: (id: string) =>
    request<RelationshipDetail[]>(`/api/entities/${id}/relationships`),

  impact: (
    workspaceId: string,
    entityId: string,
    params: { direction?: string; max_depth?: number | null } = {},
  ) =>
    request<Impact>(
      `/api/impact/${entityId}${qs({ workspace_id: workspaceId, direction: params.direction ?? "downstream", max_depth: params.max_depth ?? undefined })}`,
    ),

  traverse: (
    workspaceId: string,
    entityId: string,
    params: { direction?: string; max_depth?: number | null } = {},
  ) =>
    request<Traversal>(
      `/api/traverse/${entityId}${qs({ workspace_id: workspaceId, direction: params.direction ?? "downstream", max_depth: params.max_depth ?? undefined })}`,
    ),

  neighbours: (workspaceId: string, entityId: string) =>
    request<Traversal>(`/api/graph/neighbours/${entityId}${qs({ workspace_id: workspaceId })}`),

  path: (workspaceId: string, sourceId: string, targetId: string) =>
    request<PathResult>(
      `/api/path${qs({ workspace_id: workspaceId, source_id: sourceId, target_id: targetId })}`,
    ),

  search: (workspaceId: string, q: string, limit = 30) =>
    request<SearchResponse>(`/api/search${qs({ workspace_id: workspaceId, q, limit })}`),

  risks: (workspaceId: string, opts: { recompute?: boolean } = {}) =>
    request<{ total: number; by_severity: Record<string, number>; findings: RiskFinding[] }>(
      `/api/risks${qs({ workspace_id: workspaceId, recompute: opts.recompute || undefined })}`,
    ),

  scans: {
    list: (workspaceId?: string) =>
      request<ScanProgress[]>(`/api/scans${qs({ workspace_id: workspaceId })}`),
    get: (id: string) => request<ScanProgress>(`/api/scans/${id}`),
    run: (payload: { root_path: string; workspace_id?: string; workspace_name?: string }) =>
      request<ScanProgress>("/api/scans", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      }),
  },
};
