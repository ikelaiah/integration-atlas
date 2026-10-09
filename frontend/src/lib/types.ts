/** Typed mirrors of the backend Pydantic schemas. */

export type EntityType =
  | "system"
  | "application"
  | "server"
  | "database"
  | "schema"
  | "table"
  | "column"
  | "script"
  | "scheduled_job"
  | "api"
  | "endpoint"
  | "file"
  | "directory"
  | "sftp_location"
  | "queue"
  | "external_service"
  | "integration";

export type RelationshipType =
  | "reads_from"
  | "writes_to"
  | "calls"
  | "runs"
  | "runs_on"
  | "depends_on"
  | "produces"
  | "consumes"
  | "transfers_to"
  | "imports_from"
  | "exports_to"
  | "triggers"
  | "uses_table"
  | "uses_column"
  | "connects_to";

export type Confidence = "low" | "medium" | "high" | "confirmed" | "manual";
export type Severity = "info" | "low" | "medium" | "high" | "critical";
export type Environment = "production" | "test" | "development" | "unknown";
export type ReviewStatus = "proposed" | "confirmed" | "rejected";
export type SourceKind = "discovered" | "manual" | "demo";

export interface GraphNode {
  id: string;
  entity_type: EntityType;
  name: string;
  qualified_name: string;
  display_name: string;
  technology: string;
  environment: Environment;
  confidence: Confidence;
  owner: string;
  risk_level: Severity | null;
  is_missing: boolean;
  source_kind?: SourceKind;
  degree: number;
  meta_json: Record<string, unknown>;
}

export interface GraphEdge {
  id: string;
  source_id: string;
  target_id: string;
  relationship_type: RelationshipType;
  flow_from: string;
  flow_to: string;
  confidence: Confidence;
  review_status: ReviewStatus;
  label: string;
  [key: string]: unknown;
}

export interface GraphResponse {
  workspace_id: string;
  nodes: GraphNode[];
  edges: GraphEdge[];
  truncated: boolean;
  totals: Record<string, number>;
  facets: {
    entity_type: Record<string, number>;
    environment: Record<string, number>;
    relationship_type: Record<string, number>;
    review_status: Record<string, number>;
  };
}

export interface EntityDetail extends GraphNode {
  workspace_id: string;
  description: string;
  location: string;
  source_kind: SourceKind;
  created_at: string;
  updated_at: string;
}

export interface Evidence {
  id: string;
  subject_kind: "entity" | "relationship";
  evidence_kind: string;
  source_path: string;
  line_start: number | null;
  line_end: number | null;
  snippet: string;
  parser: string;
  confidence: Confidence;
  meta_json: Record<string, unknown>;
  created_at: string;
}

export interface RelationshipDetail extends GraphEdge {
  workspace_id: string;
  source: GraphNode;
  target: GraphNode;
  evidence: Evidence[];
  source_kind: SourceKind;
  label: string;
  meta_json: Record<string, unknown>;
}

export interface Step {
  entity: GraphNode;
  depth: number;
  relationship: GraphEdge | null;
}

export interface Traversal {
  root: GraphNode;
  direction: string;
  steps: Step[];
  counts_by_type: Record<string, number>;
  truncated: boolean;
}

export interface ImpactGroup {
  entity_type: EntityType;
  label: string;
  count: number;
  entities: GraphNode[];
}

export interface Impact {
  root: GraphNode;
  direction: string;
  max_depth: number | null;
  total_affected: number;
  groups: ImpactGroup[];
  integrations: number;
  scripts: number;
  jobs: number;
  files: number;
  external_services: number;
  databases: number;
  other: number;
  chains: Step[][];
  truncated: boolean;
}

export interface PathResult {
  found: boolean;
  mode: "downstream" | "upstream" | "connected" | "none";
  from_entity: GraphNode | null;
  to_entity: GraphNode | null;
  steps: Step[];
  length: number;
}

export interface SearchHit {
  entity: GraphNode;
  score: number;
  matched_on: string;
}

export interface SearchResponse {
  query: string;
  hits: SearchHit[];
  total: number;
}

export interface Workspace {
  id: string;
  name: string;
  slug: string;
  description: string;
  is_demo: boolean;
  created_at: string;
  updated_at: string;
}

export interface RiskFinding {
  id: string;
  workspace_id: string;
  rule_id: string;
  rule_name: string;
  severity: Severity;
  title: string;
  reason: string;
  entity_id: string | null;
  relationship_id: string | null;
  status: string;
  details_json: Record<string, unknown>;
  created_at: string;
}

export interface RiskSummary {
  total: number;
  by_severity: Record<string, number>;
  findings: RiskFinding[];
}

export interface Overview {
  workspace: Workspace;
  entity_counts: Record<string, number>;
  relationship_counts: Record<string, number>;
  totals: Record<string, number>;
  confidence: Record<string, number>;
  environments: Record<string, number>;
  risk_summary: {
    total: number;
    by_severity: Record<string, number>;
  };
  highlights: string[];
}

export interface ScanProgress {
  scan: {
    id: string;
    workspace_id: string;
    root_path: string;
    status: string;
    scanner_summary: Record<string, unknown>;
    diff_summary: Record<string, unknown>;
    error: string;
    started_at: string | null;
    finished_at: string | null;
  };
  files_discovered: number;
  files_parsed: number;
  by_extension: Record<string, number>;
  entities: number;
  relationships: number;
  secrets_redacted: number;
  warnings: number;
  events: string[];
}

export interface ScanChange {
  kind: "entity" | "relationship";
  action: "added" | "updated" | "removed";
  id: string;
  type: string;
  name: string;
}

export interface ScanDiff {
  entities: Record<"added" | "updated" | "removed", number>;
  relationships: Record<"added" | "updated" | "removed", number>;
  total: number;
  changes: ScanChange[];
  truncated: boolean;
}

export interface ScanPreview {
  scanner_summary: Record<string, unknown>;
  diff_summary: ScanDiff;
}

export interface ReviewPage {
  items: RelationshipDetail[];
  total: number;
  limit: number;
  offset: number;
}
