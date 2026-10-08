import type { Confidence, EntityType, RelationshipType, Severity } from "./types";

export interface EntityVisual {
  color: string;
  /** Tailwind-safe CSS custom property name. */
  varName: string;
  label: string;
  short: string;
  /** Node shape hint used by the graph renderer. */
  shape: "rounded" | "pill" | "square" | "diamond" | "hex";
  /** Larger nodes belong higher in the hierarchy. */
  scale: number;
}

const C = {
  system: "#2dd4bf",
  application: "#a78bfa",
  server: "#fb7185",
  database: "#60a5fa",
  schema: "#38bdf8",
  table: "#60a5fa",
  column: "#7dd3fc",
  script: "#22d3ee",
  scheduled_job: "#fbbf24",
  api: "#4ade80",
  endpoint: "#34d399",
  file: "#94a3b8",
  directory: "#cbd5e1",
  sftp_location: "#8fa3b8",
  queue: "#fb923c",
  external_service: "#818cf8",
  integration: "#c084fc",
  unknown: "#6b7280",
} as const;

export const ENTITY_VISUALS: Record<EntityType, EntityVisual> = {
  system: { color: C.system, varName: "--color-e-system", label: "System", short: "SYS", shape: "hex", scale: 1.35 },
  application: { color: C.application, varName: "--color-e-application", label: "Application", short: "APP", shape: "rounded", scale: 1.15 },
  server: { color: C.server, varName: "--color-e-server", label: "Server", short: "SRV", shape: "square", scale: 1.1 },
  database: { color: C.database, varName: "--color-e-database", label: "Database", short: "DB", shape: "rounded", scale: 1.15 },
  schema: { color: C.schema, varName: "--color-e-schema", label: "Schema", short: "SCH", shape: "rounded", scale: 0.9 },
  table: { color: C.table, varName: "--color-e-table", label: "Table", short: "TBL", shape: "rounded", scale: 0.95 },
  column: { color: C.column, varName: "--color-e-column", label: "Column", short: "COL", shape: "pill", scale: 0.72 },
  script: { color: C.script, varName: "--color-e-script", label: "Script", short: "SCR", shape: "rounded", scale: 1.0 },
  scheduled_job: { color: C.scheduled_job, varName: "--color-e-scheduled_job", label: "Scheduled Job", short: "JOB", shape: "pill", scale: 1.0 },
  api: { color: C.api, varName: "--color-e-api", label: "API", short: "API", shape: "rounded", scale: 1.05 },
  endpoint: { color: C.endpoint, varName: "--color-e-endpoint", label: "Endpoint", short: "END", shape: "pill", scale: 0.85 },
  file: { color: C.file, varName: "--color-e-file", label: "File", short: "FILE", shape: "square", scale: 0.95 },
  directory: { color: C.directory, varName: "--color-e-directory", label: "Directory", short: "DIR", shape: "square", scale: 0.85 },
  sftp_location: { color: C.sftp_location, varName: "--color-e-sftp_location", label: "SFTP Location", short: "SFTP", shape: "square", scale: 0.9 },
  queue: { color: C.queue, varName: "--color-e-queue", label: "Queue", short: "Q", shape: "diamond", scale: 0.9 },
  external_service: { color: C.external_service, varName: "--color-e-external_service", label: "External Service", short: "EXT", shape: "hex", scale: 1.2 },
  integration: { color: C.integration, varName: "--color-e-integration", label: "Integration", short: "INT", shape: "rounded", scale: 1.1 },
};

export const ENTITY_TYPE_ORDER: EntityType[] = [
  "system",
  "application",
  "external_service",
  "integration",
  "database",
  "schema",
  "table",
  "column",
  "api",
  "endpoint",
  "script",
  "scheduled_job",
  "file",
  "directory",
  "sftp_location",
  "queue",
  "server",
];

export function entityVisual(type: EntityType | string): EntityVisual {
  return ENTITY_VISUALS[type as EntityType] ?? {
    color: C.unknown,
    varName: "--color-e-unknown",
    label: "Unknown",
    short: "?",
    shape: "rounded",
    scale: 1,
  };
}

export const CONFIDENCE_META: Record<Confidence, { label: string; color: string; rank: number }> = {
  low: { label: "Low", color: "#6b7280", rank: 1 },
  medium: { label: "Medium", color: "#fbbf24", rank: 2 },
  high: { label: "High", color: "#60a5fa", rank: 3 },
  confirmed: { label: "Confirmed", color: "#34d399", rank: 4 },
  manual: { label: "Manual", color: "#c084fc", rank: 5 },
};

export const SEVERITY_META: Record<Severity, { label: string; color: string; rank: number }> = {
  info: { label: "Info", color: "#60a5fa", rank: 0 },
  low: { label: "Low", color: "#94a3b8", rank: 1 },
  medium: { label: "Medium", color: "#fbbf24", rank: 2 },
  high: { label: "High", color: "#fb923c", rank: 3 },
  critical: { label: "Critical", color: "#f87171", rank: 4 },
};

export const RELATIONSHIP_META: Record<
  RelationshipType,
  { label: string; short: string; flow: "forward" | "reverse" | "both"; arrow: string }
> = {
  reads_from: { label: "Reads from", short: "READS", flow: "reverse", arrow: "read by" },
  writes_to: { label: "Writes to", short: "WRITES", flow: "forward", arrow: "writes to" },
  calls: { label: "Calls", short: "CALLS", flow: "both", arrow: "couples" },
  runs: { label: "Runs", short: "RUNS", flow: "reverse", arrow: "run by" },
  runs_on: { label: "Runs on", short: "HOST", flow: "reverse", arrow: "hosts" },
  depends_on: { label: "Depends on", short: "DEPS", flow: "reverse", arrow: "required by" },
  produces: { label: "Produces", short: "PROD", flow: "forward", arrow: "produces" },
  consumes: { label: "Consumes", short: "CONS", flow: "reverse", arrow: "consumed by" },
  transfers_to: { label: "Transfers to", short: "XFER", flow: "forward", arrow: "transfers to" },
  imports_from: { label: "Imports from", short: "IMPORT", flow: "reverse", arrow: "imported by" },
  exports_to: { label: "Exports to", short: "EXPORT", flow: "forward", arrow: "exports to" },
  triggers: { label: "Triggers", short: "TRIG", flow: "forward", arrow: "triggers" },
  uses_table: { label: "Uses table", short: "TBL", flow: "reverse", arrow: "used by" },
  uses_column: { label: "Uses column", short: "COL", flow: "reverse", arrow: "used by" },
  connects_to: { label: "Connects to", short: "CONN", flow: "reverse", arrow: "linked to" },
};
