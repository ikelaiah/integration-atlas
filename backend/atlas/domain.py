"""Core domain vocabulary.

Pure-Python enums and semantics tables with no I/O and no third-party
dependencies. Everything else in the codebase imports from here so that the
vocabulary of the product is defined exactly once.

Flow semantics
--------------
Relationships are stored in the direction that reads naturally in English::

    student_export.py  --READS_FROM-->  LegacySIS.Student.Person

But *impact* flows the other way: if the table changes, the script is what
breaks. Each relationship type therefore declares a :class:`Flow`:

``Flow.REVERSE``
    Influence flows ``target -> source``. The source depends on the target.
    (READS_FROM, CONSUMES, DEPENDS_ON, USES_TABLE, ...)

``Flow.FORWARD``
    Influence flows ``source -> target``. The target depends on the source.
    (PRODUCES, WRITES_TO, EXPORTS_TO, TRIGGERS, ...)

Impact analysis traverses the *influence* direction. Dependency discovery
("what does X need?") traverses the opposite direction. See
``docs/adr/002-relationship-flow-semantics.md``.
"""

from __future__ import annotations

from enum import Enum
from typing import Final


class EntityType(str, Enum):
    """The kinds of thing that can appear in the integration graph."""

    SYSTEM = "system"
    APPLICATION = "application"
    SERVER = "server"
    DATABASE = "database"
    SCHEMA = "schema"
    TABLE = "table"
    COLUMN = "column"
    SCRIPT = "script"
    SCHEDULED_JOB = "scheduled_job"
    API = "api"
    ENDPOINT = "endpoint"
    FILE = "file"
    DIRECTORY = "directory"
    SFTP_LOCATION = "sftp_location"
    QUEUE = "queue"
    EXTERNAL_SERVICE = "external_service"
    INTEGRATION = "integration"

    @property
    def label(self) -> str:
        return _ENTITY_TYPE_LABELS[self]


_ENTITY_TYPE_LABELS: Final[dict[EntityType, str]] = {
    EntityType.SYSTEM: "System",
    EntityType.APPLICATION: "Application",
    EntityType.SERVER: "Server",
    EntityType.DATABASE: "Database",
    EntityType.SCHEMA: "Schema",
    EntityType.TABLE: "Table",
    EntityType.COLUMN: "Column",
    EntityType.SCRIPT: "Script",
    EntityType.SCHEDULED_JOB: "Scheduled Job",
    EntityType.API: "API",
    EntityType.ENDPOINT: "Endpoint",
    EntityType.FILE: "File",
    EntityType.DIRECTORY: "Directory",
    EntityType.SFTP_LOCATION: "SFTP Location",
    EntityType.QUEUE: "Queue",
    EntityType.EXTERNAL_SERVICE: "External Service",
    EntityType.INTEGRATION: "Integration",
}


class RelationshipType(str, Enum):
    """Named verbs describing how one entity relates to another."""

    READS_FROM = "reads_from"
    WRITES_TO = "writes_to"
    CALLS = "calls"
    RUNS = "runs"
    RUNS_ON = "runs_on"
    DEPENDS_ON = "depends_on"
    PRODUCES = "produces"
    CONSUMES = "consumes"
    TRANSFERS_TO = "transfers_to"
    IMPORTS_FROM = "imports_from"
    EXPORTS_TO = "exports_to"
    TRIGGERS = "triggers"
    USES_TABLE = "uses_table"
    USES_COLUMN = "uses_column"
    CONNECTS_TO = "connects_to"

    @property
    def label(self) -> str:
        return _RELATIONSHIP_TYPE_LABELS[self]

    @property
    def flow(self) -> Flow:
        return RELATIONSHIP_FLOW[self]


_RELATIONSHIP_TYPE_LABELS: Final[dict[RelationshipType, str]] = {
    RelationshipType.READS_FROM: "Reads from",
    RelationshipType.WRITES_TO: "Writes to",
    RelationshipType.CALLS: "Calls",
    RelationshipType.RUNS: "Runs",
    RelationshipType.RUNS_ON: "Runs on",
    RelationshipType.DEPENDS_ON: "Depends on",
    RelationshipType.PRODUCES: "Produces",
    RelationshipType.CONSUMES: "Consumes",
    RelationshipType.TRANSFERS_TO: "Transfers to",
    RelationshipType.IMPORTS_FROM: "Imports from",
    RelationshipType.EXPORTS_TO: "Exports to",
    RelationshipType.TRIGGERS: "Triggers",
    RelationshipType.USES_TABLE: "Uses table",
    RelationshipType.USES_COLUMN: "Uses column",
    RelationshipType.CONNECTS_TO: "Connects to",
}


class Flow(str, Enum):
    """Direction in which influence travels along a relationship edge."""

    FORWARD = "forward"
    REVERSE = "reverse"
    BOTH = "both"


#: Direction of influence for every relationship type. Changing ``target``
#: propagates to ``source`` for REVERSE, to ``target`` for FORWARD, and to
#: both ends for BOTH.
RELATIONSHIP_FLOW: Final[dict[RelationshipType, Flow]] = {
    RelationshipType.READS_FROM: Flow.REVERSE,
    RelationshipType.WRITES_TO: Flow.FORWARD,
    # A call couples both ends: a change in the caller can break the callee's
    # contract, and a change in the callee breaks the caller.
    RelationshipType.CALLS: Flow.BOTH,
    RelationshipType.RUNS: Flow.REVERSE,
    RelationshipType.RUNS_ON: Flow.REVERSE,
    RelationshipType.DEPENDS_ON: Flow.REVERSE,
    RelationshipType.PRODUCES: Flow.FORWARD,
    RelationshipType.CONSUMES: Flow.REVERSE,
    RelationshipType.TRANSFERS_TO: Flow.FORWARD,
    RelationshipType.IMPORTS_FROM: Flow.REVERSE,
    RelationshipType.EXPORTS_TO: Flow.FORWARD,
    RelationshipType.TRIGGERS: Flow.FORWARD,
    RelationshipType.USES_TABLE: Flow.REVERSE,
    RelationshipType.USES_COLUMN: Flow.REVERSE,
    RelationshipType.CONNECTS_TO: Flow.REVERSE,
}


class Confidence(str, Enum):
    """How sure Atlas is about a discovery. Ordered weakest to strongest."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CONFIRMED = "confirmed"
    MANUAL = "manual"

    @property
    def label(self) -> str:
        return _CONFIDENCE_LABELS[self]

    @property
    def rank(self) -> int:
        return _CONFIDENCE_RANK[self]


_CONFIDENCE_LABELS: Final[dict[Confidence, str]] = {
    Confidence.LOW: "Low",
    Confidence.MEDIUM: "Medium",
    Confidence.HIGH: "High",
    Confidence.CONFIRMED: "Confirmed",
    Confidence.MANUAL: "Manual",
}

_CONFIDENCE_RANK: Final[dict[Confidence, int]] = {
    Confidence.LOW: 1,
    Confidence.MEDIUM: 2,
    Confidence.HIGH: 3,
    Confidence.CONFIRMED: 4,
    Confidence.MANUAL: 5,
}

#: Confidence levels at or above which a discovery counts as "trustworthy"
#: for filtering purposes.
CONFIDENCE_STRONG: Final[frozenset[Confidence]] = frozenset(
    {Confidence.HIGH, Confidence.CONFIRMED, Confidence.MANUAL}
)


class Severity(str, Enum):
    """Risk finding severity. Ordered weakest to strongest."""

    INFO = "info"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"

    @property
    def label(self) -> str:
        return _SEVERITY_LABELS[self]

    @property
    def rank(self) -> int:
        return _SEVERITY_RANK[self]


_SEVERITY_LABELS: Final[dict[Severity, str]] = {
    Severity.INFO: "Info",
    Severity.LOW: "Low",
    Severity.MEDIUM: "Medium",
    Severity.HIGH: "High",
    Severity.CRITICAL: "Critical",
}

_SEVERITY_RANK: Final[dict[Severity, int]] = {
    Severity.INFO: 0,
    Severity.LOW: 1,
    Severity.MEDIUM: 2,
    Severity.HIGH: 3,
    Severity.CRITICAL: 4,
}


class Environment(str, Enum):
    PRODUCTION = "production"
    TEST = "test"
    DEVELOPMENT = "development"
    UNKNOWN = "unknown"


class SourceKind(str, Enum):
    """Where a piece of knowledge came from."""

    DISCOVERED = "discovered"
    MANUAL = "manual"
    DEMO = "demo"


#: Entity fields a human may edit through the API. Once one of these is marked
#: as a manual override, discovery never clobbers it on a later rescan.
MANUAL_PROTECTED_FIELDS: Final[frozenset[str]] = frozenset(
    {
        "name",
        "qualified_name",
        "description",
        "owner",
        "environment",
        "location",
        "technology",
        "confidence",
        "meta_json",
    }
)


class ReviewStatus(str, Enum):
    """User verdict on a discovered relationship."""

    PROPOSED = "proposed"
    CONFIRMED = "confirmed"
    REJECTED = "rejected"


class EvidenceKind(str, Enum):
    """What sort of proof backs a discovery."""

    SOURCE_LINE = "source_line"
    CONFIG_KEY = "config_key"
    CONNECTION_STRING = "connection_string"
    SQL_STATEMENT = "sql_statement"
    URL = "url"
    FILE_PATH = "file_path"
    SCHEDULER_ENTRY = "scheduler_entry"
    CRON_EXPRESSION = "cron_expression"
    IMPORT = "import"
    MANUAL_NOTE = "manual_note"
    INFERRED = "inferred"


class SubjectKind(str, Enum):
    ENTITY = "entity"
    RELATIONSHIP = "relationship"


class ScanStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class RiskStatus(str, Enum):
    OPEN = "open"
    ACKNOWLEDGED = "acknowledged"
    DISMISSED = "dismissed"


class ScannerFindingKind(str, Enum):
    """Kinds of raw observation emitted by a scanner before normalisation."""

    ENTITY_CANDIDATE = "entity_candidate"
    RELATIONSHIP_CANDIDATE = "relationship_candidate"
    SECRET_REDACTED = "secret_redacted"
    WARNING = "warning"
