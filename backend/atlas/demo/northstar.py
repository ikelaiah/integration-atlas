"""Northstar Education Group — a realistic fictional enterprise demo.

Everything here is *fabricated* but shaped like a real mid-size education
group: a legacy DB2 student information system that nobody wants to touch, a
modern enrolment portal, a finance ERP, a handful of SaaS systems, Windows
scheduled jobs, cron jobs, CSV drops over SFTP and REST integrations.

The estate is built around one deliberately messy story:

``LegacySIS.Student.Person.StudentID`` feeds a nightly CSV export which is
consumed by *two* independent integrations. Changing the column therefore has
downstream effects that are not written down anywhere.

Load it with ``atlas demo`` or ``POST /api/workspaces/{id}/seed-demo``.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from atlas.domain import (
    Confidence,
    EntityType,
    Environment,
    EvidenceKind,
    RelationshipType,
)
from atlas.services.redaction import redact

ORG = "Northstar Education Group"


@dataclass
class EntitySpec:
    key: str
    entity_type: EntityType
    name: str
    qualified_name: str = ""
    description: str = ""
    owner: str = ""
    environment: Environment = Environment.PRODUCTION
    location: str = ""
    technology: str = ""
    confidence: Confidence = Confidence.HIGH
    is_missing: bool = False
    meta: dict = field(default_factory=dict)


@dataclass
class EvidenceSpec:
    kind: EvidenceKind = EvidenceKind.SOURCE_LINE
    path: str = ""
    line: int | None = None
    snippet: str = ""
    parser: str = "demo"
    confidence: Confidence = Confidence.HIGH


@dataclass
class RelSpec:
    source: str
    target: str
    rel_type: RelationshipType
    label: str = ""
    confidence: Confidence = Confidence.HIGH
    evidence: list[EvidenceSpec] = field(default_factory=list)


def _ev(path: str, line: int, snippet: str, kind: EvidenceKind = EvidenceKind.SOURCE_LINE) -> EvidenceSpec:
    return EvidenceSpec(kind=kind, path=path, line=line, snippet=snippet)


# --------------------------------------------------------------------------- #
# Entities
# --------------------------------------------------------------------------- #
ENTITY_SPECS: list[EntitySpec] = [
    # -- servers ------------------------------------------------------------
    EntitySpec("app01", EntityType.SERVER, "APP-SERVER-01", "APP-SERVER-01",
               "Windows Server 2019 hosting the integration scheduled tasks.",
               owner="Platform Team", technology="Windows Server",
               meta={"os": "Windows Server 2019", "role": "integration-host"}),
    EntitySpec("sql01", EntityType.SERVER, "SQL-PROD-01", "SQL-PROD-01",
               "Production SQL Server 2019 cluster.", owner="Data Platform",
               technology="SQL Server 2019"),
    EntitySpec("sqldev", EntityType.SERVER, "SQL-DEV-01", "SQL-DEV-01",
               "Development SQL Server.", owner="Data Platform",
               technology="SQL Server 2019", environment=Environment.DEVELOPMENT),
    EntitySpec("db2", EntityType.SERVER, "DB2-LEGACY-01", "DB2-LEGACY-01",
               "DB2 for z/OS hosting the legacy student information system.",
               owner="Legacy Ops", technology="DB2 11"),
    EntitySpec("batch01", EntityType.SERVER, "BATCH-01", "BATCH-01",
               "Linux batch host running the cron-based Python integrations.",
               owner="Platform Team", technology="RHEL 8"),
    EntitySpec("sftp01", EntityType.SERVER, "SFTP-01", "SFTP-01",
               "Managed file transfer gateway for partner exchanges.",
               owner="Integration Team", technology="OpenSSH"),
    EntitySpec("web01", EntityType.SERVER, "WEB-01", "WEB-01",
               "IIS web front end.", owner="Digital Team", technology="IIS 10"),

    # -- systems ------------------------------------------------------------
    EntitySpec("legacysis", EntityType.SYSTEM, "LegacySIS", "LegacySIS",
               "Legacy student information system. In service since 2004; "
               "schedules, enrolments and student demographics all live here.",
               owner="Student Administration", technology="DB2 / COBOL",
               meta={"vendor": "EduSystems", "support_status": "extended"}),
    EntitySpec("portal", EntityType.SYSTEM, "EnrolmentPortal", "EnrolmentPortal",
               "Public-facing enrolment portal for new families.",
               owner="Digital Team", technology="Python / FastAPI / PostgreSQL"),
    EntitySpec("finance", EntityType.SYSTEM, "FinancePro", "FinancePro",
               "Finance ERP: fee schedules, invoicing and the general ledger.",
               owner="Finance Systems", technology="SQL Server"),
    EntitySpec("identity", EntityType.SYSTEM, "IdentityHub", "IdentityHub",
               "Identity provisioning and directory synchronisation.",
               owner="Identity Team", technology="SCIM / LDAP"),
    EntitySpec("learning", EntityType.EXTERNAL_SERVICE, "LearningCloud", "LearningCloud",
               "SaaS learning management system.", owner="Learning Technologies",
               technology="SaaS", environment=Environment.PRODUCTION,
               meta={"vendor": "LearningCloud Inc.", "contract_renews": "2027-06-30"}),
    EntitySpec("payroll", EntityType.EXTERNAL_SERVICE, "PayrollPlus", "PayrollPlus",
               "SaaS payroll platform.", owner="People & Culture",
               technology="SaaS", meta={"vendor": "PayrollPlus Ltd"}),
    EntitySpec("docs", EntityType.APPLICATION, "DocumentStore", "DocumentStore",
               "Document management and records retention.", owner="Records Team",
               technology="SharePoint"),
    EntitySpec("reporting", EntityType.DATABASE, "ReportingMart", "ReportingMart",
               "Reporting data mart fed nightly from the operational systems.",
               owner="Data Platform", technology="SQL Server"),
    EntitySpec("comms", EntityType.EXTERNAL_SERVICE, "CommsGateway", "CommsGateway",
               "Email and SMS gateway for family communications.",
               owner="Communications", technology="SMTP / REST"),
    EntitySpec("crm", EntityType.EXTERNAL_SERVICE, "AdmissionsCRM", "AdmissionsCRM",
               "SaaS admissions and marketing CRM.", owner="Admissions",
               technology="SaaS", meta={"vendor": "AdmitWise"}),
    EntitySpec("library", EntityType.APPLICATION, "LibraryHub", "LibraryHub",
               "Library management system.", owner="Library", technology="Java / Oracle"),
    EntitySpec("timetable", EntityType.APPLICATION, "TimetableEngine", "TimetableEngine",
               "Timetabling and room scheduling.", owner="Curriculum", technology=".NET"),
    EntitySpec("transport", EntityType.EXTERNAL_SERVICE, "TransportTracker", "TransportTracker",
               "School bus tracking and parent notifications.", owner="Operations",
               technology="SaaS"),
    EntitySpec("website", EntityType.APPLICATION, "WebsiteCMS", "WebsiteCMS",
               "Public website and content management.", owner="Digital Team",
               technology="WordPress"),

    # -- applications -------------------------------------------------------
    EntitySpec("hubapp", EntityType.APPLICATION, "Northstar Integration Hub",
               "Northstar Integration Hub",
               "Home-grown integration application that hosts the nightly jobs.",
               owner="Integration Team", technology="Python / PowerShell",
               meta={"repo": "git@northstar:platform/integration-hub.git"}),
    EntitySpec("svcconsole", EntityType.APPLICATION, "Student Services Console",
               "Student Services Console",
               "Internal console used by student services staff.",
               owner="Student Administration", technology=".NET"),

    # -- databases / schemas / tables / columns -----------------------------
    EntitySpec("db_sis", EntityType.DATABASE, "LegacySIS", "LegacySIS",
               "DB2 database backing LegacySIS.", owner="Legacy Ops",
               technology="DB2", location="DB2-LEGACY-01/LegacySIS"),
    EntitySpec("sch_student", EntityType.SCHEMA, "Student", "LegacySIS.Student",
               "Student schema in the legacy database.", owner="Legacy Ops",
               technology="DB2"),
    EntitySpec("sch_admin", EntityType.SCHEMA, "Admin", "LegacySIS.Admin",
               "Administrative tables and archives.", owner="Legacy Ops",
               technology="DB2"),

    EntitySpec("t_person", EntityType.TABLE, "Person", "LegacySIS.Student.Person",
               "Core student demographic record. One row per student.",
               owner="Legacy Ops", technology="DB2",
               meta={"approx_rows": "42,000", "updated": "nightly"}),
    EntitySpec("t_enrol", EntityType.TABLE, "Enrolment", "LegacySIS.Student.Enrolment",
               "Year-level enrolment records.", owner="Legacy Ops", technology="DB2",
               meta={"approx_rows": "180,000"}),
    EntitySpec("t_contact", EntityType.TABLE, "Contact", "LegacySIS.Student.Contact",
               "Parent and guardian contact details.", owner="Legacy Ops", technology="DB2"),
    EntitySpec("t_archive", EntityType.TABLE, "StudentArchive", "LegacySIS.Admin.StudentArchive",
               "Historic student rows retained for compliance.", owner="Legacy Ops",
               technology="DB2"),

    EntitySpec("c_studentid", EntityType.COLUMN, "StudentID", "LegacySIS.Student.Person.StudentID",
               "Primary key of the student record. Referenced by nearly every integration.",
               owner="Legacy Ops", technology="DB2",
               meta={"data_type": "CHAR(10)", "nullable": False, "primary_key": True}),
    EntitySpec("c_firstname", EntityType.COLUMN, "FirstName", "LegacySIS.Student.Person.FirstName",
               "Legal given name.", owner="Legacy Ops", technology="DB2",
               meta={"data_type": "VARCHAR(60)"}),
    EntitySpec("c_lastname", EntityType.COLUMN, "LastName", "LegacySIS.Student.Person.LastName",
               "Legal family name.", owner="Legacy Ops", technology="DB2",
               meta={"data_type": "VARCHAR(60)"}),
    EntitySpec("c_dob", EntityType.COLUMN, "DateOfBirth", "LegacySIS.Student.Person.DateOfBirth",
               "Date of birth.", owner="Legacy Ops", technology="DB2",
               meta={"data_type": "DATE"}),
    EntitySpec("c_yearlevel", EntityType.COLUMN, "YearLevel", "LegacySIS.Student.Person.YearLevel",
               "Current year level (K-12).", owner="Legacy Ops", technology="DB2",
               meta={"data_type": "SMALLINT"}),
    EntitySpec("c_campus", EntityType.COLUMN, "CampusCode", "LegacySIS.Student.Person.CampusCode",
               "Campus the student attends.", owner="Legacy Ops", technology="DB2",
               meta={"data_type": "CHAR(4)"}),

    EntitySpec("db_fin", EntityType.DATABASE, "FinancePro", "FinancePro",
               "Finance ERP database.", owner="Finance Systems", technology="SQL Server",
               location="SQL-PROD-01/FinancePro"),
    EntitySpec("sch_finance", EntityType.SCHEMA, "Finance", "FinancePro.Finance",
               "Finance schema.", owner="Finance Systems", technology="SQL Server"),
    EntitySpec("t_invoice", EntityType.TABLE, "Invoice", "FinancePro.Finance.Invoice",
               "Family fee invoices.", owner="Finance Systems", technology="SQL Server"),
    EntitySpec("t_ledger", EntityType.TABLE, "Ledger", "FinancePro.Finance.Ledger",
               "General ledger postings.", owner="Finance Systems", technology="SQL Server"),
    EntitySpec("t_fee", EntityType.TABLE, "FeeSchedule", "FinancePro.Finance.FeeSchedule",
               "Annual fee schedule by year level and campus.", owner="Finance Systems",
               technology="SQL Server"),

    EntitySpec("sch_mart", EntityType.SCHEMA, "mart", "ReportingMart.mart",
               "Star schema used for reporting.", owner="Data Platform",
               technology="SQL Server"),
    EntitySpec("t_dim_student", EntityType.TABLE, "dim_student", "ReportingMart.mart.dim_student",
               "Student dimension, conformed across sources.", owner="Data Platform",
               technology="SQL Server"),
    EntitySpec("t_fact_enrol", EntityType.TABLE, "fact_enrolment", "ReportingMart.mart.fact_enrolment",
               "Enrolment fact table.", owner="Data Platform", technology="SQL Server"),
    EntitySpec("t_fact_fees", EntityType.TABLE, "fact_fees", "ReportingMart.mart.fact_fees",
               "Fee fact table.", owner="Data Platform", technology="SQL Server"),

    EntitySpec("db_portal", EntityType.DATABASE, "PortalDB", "PortalDB",
               "PostgreSQL database behind the enrolment portal.",
               owner="Digital Team", technology="PostgreSQL",
               location="SQL-PROD-01:5432/portal"),
    EntitySpec("sch_portal", EntityType.SCHEMA, "portal", "PortalDB.portal",
               "Portal application schema.", owner="Digital Team", technology="PostgreSQL"),
    EntitySpec("t_applications", EntityType.TABLE, "applications", "PortalDB.portal.applications",
               "Enrolment applications submitted online.", owner="Digital Team",
               technology="PostgreSQL"),
    EntitySpec("t_applicants", EntityType.TABLE, "applicants", "PortalDB.portal.applicants",
               "Applicant identity records.", owner="Digital Team", technology="PostgreSQL"),

    # -- scripts ------------------------------------------------------------
    EntitySpec("sql_extract", EntityType.SCRIPT, "student_extract.sql",
               "/integrations/student/student_extract.sql",
               "Extracts the current student cohort from LegacySIS.",
               owner="Integration Team", technology="SQL",
               location="/integrations/student/student_extract.sql"),
    EntitySpec("ps_export", EntityType.SCRIPT, "export_students.ps1",
               "/integrations/student/export_students.ps1",
               "Runs the extract and writes students.csv to the shared drop folder.",
               owner="Integration Team", technology="PowerShell",
               location="/integrations/student/export_students.ps1"),
    EntitySpec("py_identity", EntityType.SCRIPT, "identity_sync.py",
               "/integrations/identity/identity_sync.py",
               "Reads students.csv and provisions accounts in IdentityHub.",
               owner="Identity Team", technology="Python",
               location="/integrations/identity/identity_sync.py"),
    EntitySpec("py_enrol", EntityType.SCRIPT, "nightly_sync.py",
               "/integrations/enrolment/nightly_sync.py",
               "Pushes student records into the EnrolmentPortal REST API.",
               owner="Digital Team", technology="Python",
               location="/integrations/enrolment/nightly_sync.py"),
    EntitySpec("py_finance", EntityType.SCRIPT, "finance_extract.py",
               "/integrations/finance/finance_extract.py",
               "Extracts fee and invoice data for the reporting mart.",
               owner="Finance Systems", technology="Python",
               location="/integrations/finance/finance_extract.py"),
    EntitySpec("sql_reporting", EntityType.SCRIPT, "reporting_extract.sql",
               "/integrations/reports/reporting_extract.sql",
               "Builds the student dimension and enrolment fact tables.",
               owner="Data Platform", technology="SQL",
               location="/integrations/reports/reporting_extract.sql"),
    EntitySpec("ps_hr", EntityType.SCRIPT, "hr_feed.ps1",
               "/integrations/hr/hr_feed.ps1",
               "Produces the weekly staff position feed for PayrollPlus.",
               owner="People & Culture", technology="PowerShell",
               location="/integrations/hr/hr_feed.ps1"),
    EntitySpec("py_comms", EntityType.SCRIPT, "comms_digest.py",
               "/integrations/comms/comms_digest.py",
               "Sends the daily absence and newsletter digest.",
               owner="Communications", technology="Python",
               location="/integrations/comms/comms_digest.py"),
    EntitySpec("ps_learning", EntityType.SCRIPT, "learningcloud_export.ps1",
               "/integrations/learning/learningcloud_export.ps1",
               "Exports enrolments to LearningCloud over SFTP.",
               owner="Learning Technologies", technology="PowerShell",
               location="/integrations/learning/learningcloud_export.ps1"),
    EntitySpec("py_transport", EntityType.SCRIPT, "transport_sync.py",
               "/integrations/transport/transport_sync.py",
               "Syncs student and campus data to TransportTracker.",
               owner="Operations", technology="Python",
               location="/integrations/transport/transport_sync.py"),

    # -- scheduled jobs -----------------------------------------------------
    EntitySpec("job_student", EntityType.SCHEDULED_JOB, "nightly-student-export",
               "nightly-student-export",
               "Windows scheduled task: nightly student export.",
               owner="Integration Team", technology="Windows Task Scheduler",
               meta={"schedule": "Daily 02:00", "command": "export_students.ps1",
                     "host": "APP-SERVER-01"}),
    EntitySpec("job_identity", EntityType.SCHEDULED_JOB, "identity-sync",
               "identity-sync", "cron: identity synchronisation every 15 minutes.",
               owner="Identity Team", technology="cron",
               meta={"schedule": "*/15 * * * *", "command": "identity_sync.py",
                     "host": "BATCH-01"}),
    EntitySpec("job_enrol", EntityType.SCHEDULED_JOB, "enrolment-sync",
               "enrolment-sync", "cron: hourly enrolment push.",
               owner="Digital Team", technology="cron",
               meta={"schedule": "5 * * * *", "command": "nightly_sync.py", "host": "BATCH-01"}),
    EntitySpec("job_finance", EntityType.SCHEDULED_JOB, "finance-extract",
               "finance-extract", "Windows scheduled task: finance extract.",
               owner="Finance Systems", technology="Windows Task Scheduler",
               meta={"schedule": "Daily 03:30", "command": "finance_extract.py",
                     "host": "APP-SERVER-01"}),
    EntitySpec("job_reporting", EntityType.SCHEDULED_JOB, "reporting-refresh",
               "reporting-refresh", "Windows scheduled task: reporting mart refresh.",
               owner="Data Platform", technology="SQL Server Agent",
               meta={"schedule": "Daily 04:00", "command": "reporting_extract.sql",
                     "host": "SQL-PROD-01"}),
    EntitySpec("job_hr", EntityType.SCHEDULED_JOB, "hr-feed", "hr-feed",
               "Windows scheduled task: weekly HR position feed.",
               owner="People & Culture", technology="Windows Task Scheduler",
               meta={"schedule": "Mon 06:00", "command": "hr_feed.ps1", "host": "APP-SERVER-01"}),
    EntitySpec("job_comms", EntityType.SCHEDULED_JOB, "comms-digest", "comms-digest",
               "cron: daily communications digest.",
               owner="Communications", technology="cron",
               meta={"schedule": "0 8 * * *", "command": "comms_digest.py", "host": "BATCH-01"}),
    EntitySpec("job_learning", EntityType.SCHEDULED_JOB, "learningcloud-export",
               "learningcloud-export", "Windows scheduled task: LMS export.",
               owner="Learning Technologies", technology="Windows Task Scheduler",
               meta={"schedule": "Daily 05:00", "command": "learningcloud_export.ps1",
                     "host": "APP-SERVER-01"}),
    EntitySpec("job_transport", EntityType.SCHEDULED_JOB, "transport-sync",
               "transport-sync", "cron: transport synchronisation every 10 minutes.",
               owner="Operations", technology="cron",
               meta={"schedule": "*/10 * * * *", "command": "transport_sync.py",
                     "host": "BATCH-01"}),
    EntitySpec("job_archive", EntityType.SCHEDULED_JOB, "archive-cleanup",
               "archive-cleanup", "cron: weekly archive maintenance.",
               owner="Legacy Ops", technology="cron",
               meta={"schedule": "0 1 * * 0", "command": "<unknown>", "host": "DB2-LEGACY-01"},
               is_missing=True, confidence=Confidence.MEDIUM),

    # -- files / drops / sftp ----------------------------------------------
    EntitySpec("f_students", EntityType.FILE, "students.csv", "/integrations/student/students.csv",
               "Nightly full student extract. Consumed by two independent integrations.",
               owner="Integration Team", technology="CSV",
               location="/integrations/student/students.csv",
               meta={"columns": "StudentID,FirstName,LastName,DateOfBirth,YearLevel,CampusCode",
                     "approx_rows": "42,000"}),
    EntitySpec("f_fees", EntityType.FILE, "fee_extract.csv",
               "/integrations/finance/fee_extract.csv",
               "Fee extract for the reporting mart.",
               owner="Finance Systems", technology="CSV",
               location="/integrations/finance/fee_extract.csv"),
    EntitySpec("f_hr", EntityType.FILE, "hr_positions.csv",
               "/integrations/hr/hr_positions.csv",
               "Weekly staff position feed.", owner="People & Culture", technology="CSV",
               location="/integrations/hr/hr_positions.csv"),
    EntitySpec("f_offers", EntityType.FILE, "offers.xml",
               "/integrations/enrolment/offers.xml",
               "Offer letters handed to the document store.",
               owner="Admissions", technology="XML",
               location="/integrations/enrolment/offers.xml"),
    EntitySpec("dir_drop", EntityType.DIRECTORY, "shared drop folder",
               "/integrations/student/", "Shared drop folder for student exports.",
               owner="Integration Team", location="/integrations/student/"),
    EntitySpec("dir_archive", EntityType.DIRECTORY, "archive folder",
               "/integrations/shared/archive/", "Long-term archive of export files.",
               owner="Integration Team", location="/integrations/shared/archive/"),

    EntitySpec("sftp_in", EntityType.SFTP_LOCATION, "SFTP-01:/inbound/enrolment",
               "SFTP-01:/inbound/enrolment",
               "Partner inbound drop for admissions data.",
               owner="Integration Team", technology="SFTP",
               location="SFTP-01:/inbound/enrolment"),
    EntitySpec("sftp_out", EntityType.SFTP_LOCATION, "SFTP-01:/outbound/learning",
               "SFTP-01:/outbound/learning",
               "Outbound drop consumed by LearningCloud.",
               owner="Learning Technologies", technology="SFTP",
               location="SFTP-01:/outbound/learning"),

    # -- APIs / endpoints ---------------------------------------------------
    EntitySpec("api_portal", EntityType.API, "EnrolmentPortal REST API",
               "EnrolmentPortal REST API",
               "REST API used to import student and application data.",
               owner="Digital Team", technology="REST",
               location="https://enrol.northstar.edu/api/v2"),
    EntitySpec("ep_import", EntityType.ENDPOINT, "POST /applications/import",
               "EnrolmentPortal.POST /applications/import",
               "Bulk import of student applications.", owner="Digital Team",
               technology="REST", location="https://enrol.northstar.edu/api/v2/applications/import"),
    EntitySpec("api_identity", EntityType.API, "IdentityHub SCIM API",
               "IdentityHub SCIM API",
               "SCIM 2.0 user provisioning API.", owner="Identity Team", technology="SCIM",
               location="https://identity.northstar.edu/scim/v2"),
    EntitySpec("ep_users", EntityType.ENDPOINT, "POST /Users",
               "IdentityHub.POST /Users",
               "Create a user account.", owner="Identity Team", technology="SCIM",
               location="https://identity.northstar.edu/scim/v2/Users"),
    EntitySpec("api_learning", EntityType.API, "LearningCloud API", "LearningCloud API",
               "Enrolment and course provisioning API.",
               owner="Learning Technologies", technology="REST",
               location="https://api.learningcloud.example/v1"),
    EntitySpec("api_payroll", EntityType.API, "PayrollPlus API", "PayrollPlus API",
               "Employee and position feed API.", owner="People & Culture",
               technology="REST", location="https://api.payrollplus.example/v2"),
    EntitySpec("api_crm", EntityType.API, "AdmissionsCRM API", "AdmissionsCRM API",
               "Lead and applicant synchronisation API.", owner="Admissions",
               technology="REST", location="https://api.admissionscrm.example/v1"),
    EntitySpec("api_transport", EntityType.API, "TransportTracker API",
               "TransportTracker API",
               "Student transport eligibility API.", owner="Operations",
               technology="REST", location="https://api.transporttracker.example/v1"),
    EntitySpec("api_comms", EntityType.API, "CommsGateway API", "CommsGateway API",
               "Email/SMS dispatch API.", owner="Communications", technology="REST",
               location="https://comms.northstar.edu/api/v1"),

    # -- named integrations -------------------------------------------------
    EntitySpec("int_student_portal", EntityType.INTEGRATION, "Student extract → EnrolmentPortal",
               "Student extract → EnrolmentPortal",
               "Nightly student extract loaded into the enrolment portal.",
               owner="Digital Team",
               meta={"cadence": "nightly", "criticality": "high"}),
    EntitySpec("int_student_identity", EntityType.INTEGRATION, "Student extract → IdentityHub",
               "Student extract → IdentityHub",
               "Account provisioning driven by the student extract.",
               owner="Identity Team",
               meta={"cadence": "every 15 minutes", "criticality": "high"}),
    EntitySpec("int_student_learning", EntityType.INTEGRATION, "Student extract → LearningCloud",
               "Student extract → LearningCloud",
               "Course enrolments pushed to the LMS.",
               owner="Learning Technologies", meta={"cadence": "nightly"}),
    EntitySpec("int_finance_reporting", EntityType.INTEGRATION, "Finance extract → ReportingMart",
               "Finance extract → ReportingMart",
               "Fee and invoice facts loaded into the mart.",
               owner="Data Platform", meta={"cadence": "nightly"}),
    EntitySpec("int_hr_payroll", EntityType.INTEGRATION, "HR feed → PayrollPlus",
               "HR feed → PayrollPlus", "Weekly staff position feed to payroll.",
               owner="People & Culture", meta={"cadence": "weekly"}),
    EntitySpec("int_enrolment_crm", EntityType.INTEGRATION, "EnrolmentPortal → AdmissionsCRM",
               "EnrolmentPortal → AdmissionsCRM",
               "Applicant leads synchronised to the admissions CRM.",
               owner="Admissions", meta={"cadence": "hourly"}),
    EntitySpec("int_transport", EntityType.INTEGRATION, "Student extract → TransportTracker",
               "Student extract → TransportTracker",
               "Transport eligibility computed from student and campus data.",
               owner="Operations", meta={"cadence": "every 10 minutes"}),
    EntitySpec("int_comms", EntityType.INTEGRATION, "Absence digest → CommsGateway",
               "Absence digest → CommsGateway",
               "Daily absence and newsletter digest to families.",
               owner="Communications", meta={"cadence": "daily"}),
    EntitySpec("int_archive", EntityType.INTEGRATION, "Archive cleanup",
               "Archive cleanup", "Weekly maintenance job. Owner and script unknown.",
               owner="", meta={"cadence": "weekly"}, confidence=Confidence.LOW,
               is_missing=True),
]


# --------------------------------------------------------------------------- #
# Relationships
# --------------------------------------------------------------------------- #
def _build_relationships() -> list[RelSpec]:
    e = _ev
    sis_sql = "/integrations/student/student_extract.sql"
    ps = "/integrations/student/export_students.ps1"
    ident = "/integrations/identity/identity_sync.py"
    enrol = "/integrations/enrolment/nightly_sync.py"
    fin = "/integrations/finance/finance_extract.py"
    rep = "/integrations/reports/reporting_extract.sql"

    return [
        # --- student extract pipeline --------------------------------------
        RelSpec("sql_extract", "t_person", RelationshipType.READS_FROM,
                confidence=Confidence.CONFIRMED,
                evidence=[e(sis_sql, 12, "SELECT s.StudentID, s.FirstName, s.LastName,\n"
                                          "       s.DateOfBirth, s.YearLevel, s.CampusCode\n"
                                          "FROM   Student.Person s"),
                          e(sis_sql, 21, "WHERE  s.YearLevel BETWEEN 0 AND 12")]),
        RelSpec("sql_extract", "t_enrol", RelationshipType.READS_FROM,
                confidence=Confidence.HIGH,
                evidence=[e(sis_sql, 34, "JOIN Student.Enrolment e\n"
                                          "  ON e.StudentID = s.StudentID\n"
                                          " AND e.Year = :current_year")]),
        RelSpec("sql_extract", "c_studentid", RelationshipType.USES_COLUMN,
                confidence=Confidence.CONFIRMED,
                evidence=[e(sis_sql, 13, "s.StudentID")]),
        RelSpec("sql_extract", "c_yearlevel", RelationshipType.USES_COLUMN,
                confidence=Confidence.HIGH,
                evidence=[e(sis_sql, 15, "s.YearLevel")]),
        RelSpec("sql_extract", "c_campus", RelationshipType.USES_COLUMN,
                confidence=Confidence.HIGH,
                evidence=[e(sis_sql, 16, "s.CampusCode")]),

        RelSpec("ps_export", "sql_extract", RelationshipType.RUNS,
                confidence=Confidence.CONFIRMED,
                evidence=[e(ps, 41, "Invoke-Sqlcmd -ServerInstance DB2-LEGACY-01 `\n"
                                    "  -Database LegacySIS `\n"
                                    "  -InputFile .\\student_extract.sql `\n"
                                    "  -OutputFile .\\students.csv")]),
        RelSpec("ps_export", "db_sis", RelationshipType.CONNECTS_TO,
                confidence=Confidence.HIGH,
                evidence=[e(ps, 41, "Invoke-Sqlcmd -ServerInstance DB2-LEGACY-01")]),
        RelSpec("ps_export", "app01", RelationshipType.RUNS_ON,
                confidence=Confidence.CONFIRMED,
                evidence=[e("/windows/tasks/nightly-student-export.xml", 18,
                            "<Command>powershell.exe</Command>\n"
                            "<Arguments>-File C:\\integrations\\student\\export_students.ps1</Arguments>",
                            EvidenceKind.SCHEDULER_ENTRY)]),
        RelSpec("ps_export", "f_students", RelationshipType.PRODUCES,
                confidence=Confidence.CONFIRMED,
                evidence=[e(ps, 47, "Export-Csv -Path .\\students.csv -NoTypeInformation")]),
        RelSpec("ps_export", "dir_drop", RelationshipType.WRITES_TO,
                confidence=Confidence.HIGH,
                evidence=[e(ps, 47, "Export-Csv -Path .\\students.csv")]),

        RelSpec("job_student", "ps_export", RelationshipType.RUNS,
                confidence=Confidence.CONFIRMED,
                evidence=[e("/windows/tasks/nightly-student-export.xml", 18,
                            "<Command>powershell.exe</Command>\n"
                            "<Arguments>-File C:\\integrations\\student\\export_students.ps1</Arguments>",
                            EvidenceKind.SCHEDULER_ENTRY),
                          e("/windows/tasks/nightly-student-export.xml", 31,
                            "<StartBoundary>2026-01-01T02:00:00</StartBoundary>\n"
                            "<ScheduleByDay><DaysInterval>1</DaysInterval></ScheduleByDay>",
                            EvidenceKind.SCHEDULER_ENTRY)]),
        RelSpec("job_student", "app01", RelationshipType.RUNS_ON,
                confidence=Confidence.CONFIRMED,
                evidence=[e("/windows/tasks/nightly-student-export.xml", 9,
                            "<URI>\\nightly-student-export</URI>", EvidenceKind.SCHEDULER_ENTRY)]),

        # --- identity sync (consumer #1 of students.csv) --------------------
        RelSpec("py_identity", "f_students", RelationshipType.CONSUMES,
                confidence=Confidence.CONFIRMED,
                evidence=[e(ident, 28, 'df = pd.read_csv("/integrations/student/students.csv",\n'
                                        '                  dtype={"StudentID": str})')]),
        RelSpec("py_identity", "c_studentid", RelationshipType.USES_COLUMN,
                confidence=Confidence.HIGH,
                evidence=[e(ident, 35, 'user_name = f"{row.StudentID}@northstar.edu"')]),
        RelSpec("py_identity", "api_identity", RelationshipType.CALLS,
                confidence=Confidence.CONFIRMED,
                evidence=[e(ident, 52, 'requests.post(\n'
                                        '    "https://identity.northstar.edu/scim/v2/Users",\n'
                                        '    headers={"Authorization": f"Bearer {token}"},\n'
                                        '    json=payload,\n'
                                        ')')]),
        RelSpec("py_identity", "batch01", RelationshipType.RUNS_ON,
                confidence=Confidence.HIGH,
                evidence=[e("/etc/cron.d/identity-sync", 1,
                            "*/15 * * * * svc_int /opt/integrations/identity/identity_sync.py",
                            EvidenceKind.CRON_EXPRESSION)]),
        RelSpec("job_identity", "py_identity", RelationshipType.RUNS,
                confidence=Confidence.CONFIRMED,
                evidence=[e("/etc/cron.d/identity-sync", 1,
                            "*/15 * * * * svc_int /opt/integrations/identity/identity_sync.py",
                            EvidenceKind.CRON_EXPRESSION)]),
        RelSpec("job_identity", "batch01", RelationshipType.RUNS_ON,
                confidence=Confidence.HIGH,
                evidence=[e("/etc/cron.d/identity-sync", 1,
                            "*/15 * * * * svc_int /opt/integrations/identity/identity_sync.py",
                            EvidenceKind.CRON_EXPRESSION)]),
        RelSpec("api_identity", "ep_users", RelationshipType.DEPENDS_ON,
                confidence=Confidence.HIGH,
                evidence=[e(ident, 52, "POST /scim/v2/Users")]),
        RelSpec("api_identity", "identity", RelationshipType.DEPENDS_ON,
                confidence=Confidence.HIGH,
                evidence=[e(ident, 52, "https://identity.northstar.edu/scim/v2/Users",
                            EvidenceKind.URL)]),
        RelSpec("ep_users", "identity", RelationshipType.DEPENDS_ON,
                confidence=Confidence.HIGH,
                evidence=[e(ident, 52, "https://identity.northstar.edu/scim/v2/Users",
                            EvidenceKind.URL)]),

        # --- enrolment push (consumer #2 of students.csv) -------------------
        RelSpec("py_enrol", "f_students", RelationshipType.CONSUMES,
                confidence=Confidence.CONFIRMED,
                evidence=[e(enrol, 19, 'with open("/integrations/student/students.csv") as fh:\n'
                                        '    rows = list(csv.DictReader(fh))')]),
        RelSpec("py_enrol", "api_portal", RelationshipType.CALLS,
                confidence=Confidence.CONFIRMED,
                evidence=[e(enrol, 64, 'httpx.post(\n'
                                       '    "https://enrol.northstar.edu/api/v2/applications/import",\n'
                                       '    json={"applications": payload},\n'
                                       '    timeout=60,\n'
                                       ')')]),
        RelSpec("py_enrol", "c_studentid", RelationshipType.USES_COLUMN,
                confidence=Confidence.HIGH,
                evidence=[e(enrol, 33, 'payload.append({"student_id": row["StudentID"]})')]),
        RelSpec("job_enrol", "py_enrol", RelationshipType.RUNS,
                confidence=Confidence.CONFIRMED,
                evidence=[e("/etc/cron.d/enrolment-sync", 1,
                            "5 * * * * svc_int /opt/integrations/enrolment/nightly_sync.py",
                            EvidenceKind.CRON_EXPRESSION)]),
        RelSpec("job_enrol", "batch01", RelationshipType.RUNS_ON,
                confidence=Confidence.HIGH,
                evidence=[e("/etc/cron.d/enrolment-sync", 1,
                            "5 * * * * svc_int /opt/integrations/enrolment/nightly_sync.py",
                            EvidenceKind.CRON_EXPRESSION)]),
        RelSpec("py_enrol", "batch01", RelationshipType.RUNS_ON,
                confidence=Confidence.HIGH,
                evidence=[e("/etc/cron.d/enrolment-sync", 1,
                            "5 * * * * svc_int /opt/integrations/enrolment/nightly_sync.py",
                            EvidenceKind.CRON_EXPRESSION)]),
        RelSpec("api_portal", "ep_import", RelationshipType.DEPENDS_ON,
                confidence=Confidence.HIGH),
        RelSpec("api_portal", "portal", RelationshipType.DEPENDS_ON,
                confidence=Confidence.HIGH,
                evidence=[e(enrol, 64, "https://enrol.northstar.edu/api/v2/applications/import",
                            EvidenceKind.URL)]),
        RelSpec("ep_import", "t_applications", RelationshipType.WRITES_TO,
                confidence=Confidence.MEDIUM,
                evidence=[e(enrol, 64, "POST /api/v2/applications/import", EvidenceKind.INFERRED)]),
        RelSpec("ep_import", "t_applicants", RelationshipType.WRITES_TO,
                confidence=Confidence.LOW,
                evidence=[e(enrol, 71, "applicants are upserted as a side effect",
                            EvidenceKind.INFERRED)]),

        # --- learning cloud (third consumer) --------------------------------
        RelSpec("ps_learning", "f_students", RelationshipType.CONSUMES,
                confidence=Confidence.HIGH,
                evidence=[e("/integrations/learning/learningcloud_export.ps1", 22,
                            r'Import-Csv -Path "\\APP-SERVER-01\integrations$\student\students.csv"')]),
        RelSpec("ps_learning", "sftp_out", RelationshipType.EXPORTS_TO,
                confidence=Confidence.HIGH,
                evidence=[e("/integrations/learning/learningcloud_export.ps1", 40,
                            "psftp.exe sftp.learningcloud.example -batch -b put.cmd")]),
        RelSpec("ps_learning", "app01", RelationshipType.RUNS_ON,
                confidence=Confidence.HIGH),
        RelSpec("sftp_out", "learning", RelationshipType.TRANSFERS_TO,
                confidence=Confidence.MEDIUM,
                evidence=[e("/integrations/learning/learningcloud_export.ps1", 40,
                            "sftp.learningcloud.example", EvidenceKind.INFERRED)]),
        RelSpec("api_learning", "learning", RelationshipType.DEPENDS_ON,
                confidence=Confidence.HIGH,
                evidence=[e("/integrations/learning/learningcloud_export.ps1", 44,
                            "https://api.learningcloud.example/v1/enrolments", EvidenceKind.URL)]),
        RelSpec("job_learning", "ps_learning", RelationshipType.RUNS,
                confidence=Confidence.CONFIRMED),
        RelSpec("job_learning", "app01", RelationshipType.RUNS_ON,
                confidence=Confidence.HIGH),
        RelSpec("ps_learning", "api_learning", RelationshipType.CALLS,
                confidence=Confidence.MEDIUM),

        # --- finance / reporting -------------------------------------------
        RelSpec("py_finance", "t_invoice", RelationshipType.READS_FROM,
                confidence=Confidence.CONFIRMED,
                evidence=[e(fin, 31, "SELECT InvoiceID, FamilyID, Amount, DueDate\n"
                                     "FROM   Finance.Invoice\n"
                                     "WHERE  Status <> 'CANCELLED'")]),
        RelSpec("py_finance", "t_ledger", RelationshipType.READS_FROM,
                confidence=Confidence.HIGH,
                evidence=[e(fin, 48, "SELECT PostingDate, AccountCode, Amount\n"
                                     "FROM   Finance.Ledger")]),
        RelSpec("py_finance", "t_fee", RelationshipType.READS_FROM,
                confidence=Confidence.HIGH,
                evidence=[e(fin, 57, "FROM Finance.FeeSchedule")]),
        RelSpec("py_finance", "f_fees", RelationshipType.PRODUCES,
                confidence=Confidence.CONFIRMED,
                evidence=[e(fin, 88, "df.to_csv('/integrations/finance/fee_extract.csv', index=False)")]),
        RelSpec("py_finance", "sql01", RelationshipType.CONNECTS_TO,
                confidence=Confidence.HIGH,
                evidence=[e(fin, 14, "sqlalchemy.create_engine(\n"
                                     r'    "mssql+pyodbc://SQL-PROD-01/FinancePro?driver=ODBC+Driver+17+for+SQL+Server"' + "\n"
                                     ")")]),
        RelSpec("job_finance", "py_finance", RelationshipType.RUNS,
                confidence=Confidence.CONFIRMED),
        RelSpec("job_finance", "app01", RelationshipType.RUNS_ON,
                confidence=Confidence.HIGH),

        RelSpec("sql_reporting", "t_person", RelationshipType.READS_FROM,
                confidence=Confidence.HIGH,
                evidence=[e(rep, 8, "INSERT INTO mart.dim_student (StudentID, FirstName, LastName)\n"
                                    "SELECT StudentID, FirstName, LastName FROM Student.Person")]),
        RelSpec("sql_reporting", "c_studentid", RelationshipType.USES_COLUMN,
                confidence=Confidence.HIGH,
                evidence=[e(rep, 9, "SELECT StudentID, FirstName, LastName")]),
        RelSpec("sql_reporting", "f_fees", RelationshipType.IMPORTS_FROM,
                confidence=Confidence.MEDIUM,
                evidence=[e(rep, 44, "BULK INSERT mart.fact_fees\n"
                                     "FROM '/integrations/finance/fee_extract.csv'")]),
        RelSpec("sql_reporting", "t_dim_student", RelationshipType.WRITES_TO,
                confidence=Confidence.CONFIRMED,
                evidence=[e(rep, 8, "INSERT INTO mart.dim_student")]),
        RelSpec("sql_reporting", "t_fact_enrol", RelationshipType.WRITES_TO,
                confidence=Confidence.CONFIRMED,
                evidence=[e(rep, 61, "INSERT INTO mart.fact_enrolment")]),
        RelSpec("sql_reporting", "t_fact_fees", RelationshipType.WRITES_TO,
                confidence=Confidence.CONFIRMED,
                evidence=[e(rep, 44, "BULK INSERT mart.fact_fees")]),
        RelSpec("job_reporting", "sql_reporting", RelationshipType.RUNS,
                confidence=Confidence.CONFIRMED),
        RelSpec("job_reporting", "sql01", RelationshipType.RUNS_ON,
                confidence=Confidence.HIGH),
        RelSpec("sql_reporting", "sql01", RelationshipType.CONNECTS_TO,
                confidence=Confidence.HIGH),
        RelSpec("sql_reporting", "t_enrol", RelationshipType.READS_FROM,
                confidence=Confidence.HIGH,
                evidence=[e(rep, 62, "FROM Student.Enrolment")]),

        # --- HR / payroll ---------------------------------------------------
        RelSpec("ps_hr", "f_hr", RelationshipType.PRODUCES,
                confidence=Confidence.CONFIRMED,
                evidence=[e("/integrations/hr/hr_feed.ps1", 27,
                            "Export-Csv -Path .\\hr_positions.csv -NoTypeInformation")]),
        RelSpec("ps_hr", "app01", RelationshipType.RUNS_ON, confidence=Confidence.HIGH),
        RelSpec("job_hr", "ps_hr", RelationshipType.RUNS, confidence=Confidence.CONFIRMED),
        RelSpec("job_hr", "app01", RelationshipType.RUNS_ON, confidence=Confidence.HIGH),
        RelSpec("ps_hr", "api_payroll", RelationshipType.CALLS,
                confidence=Confidence.HIGH,
                evidence=[e("/integrations/hr/hr_feed.ps1", 55,
                            "Invoke-RestMethod -Uri https://api.payrollplus.example/v2/employees `\n"
                            "  -Method Post -InFile .\\hr_positions.csv")]),
        RelSpec("api_payroll", "payroll", RelationshipType.DEPENDS_ON,
                confidence=Confidence.HIGH,
                evidence=[e("/integrations/hr/hr_feed.ps1", 55,
                            "https://api.payrollplus.example/v2/employees", EvidenceKind.URL)]),

        # --- admissions CRM -------------------------------------------------
        RelSpec("api_crm", "crm", RelationshipType.DEPENDS_ON, confidence=Confidence.HIGH),
        RelSpec("t_applications", "api_crm", RelationshipType.EXPORTS_TO,
                confidence=Confidence.MEDIUM,
                evidence=[e(enrol, 96, "push leads to the admissions CRM", EvidenceKind.INFERRED)]),

        # --- transport ------------------------------------------------------
        RelSpec("py_transport", "f_students", RelationshipType.CONSUMES,
                confidence=Confidence.HIGH),
        RelSpec("py_transport", "c_campus", RelationshipType.USES_COLUMN,
                confidence=Confidence.MEDIUM),
        RelSpec("py_transport", "api_transport", RelationshipType.CALLS,
                confidence=Confidence.HIGH),
        RelSpec("api_transport", "transport", RelationshipType.DEPENDS_ON,
                confidence=Confidence.HIGH),
        RelSpec("job_transport", "py_transport", RelationshipType.RUNS,
                confidence=Confidence.CONFIRMED),
        RelSpec("job_transport", "batch01", RelationshipType.RUNS_ON,
                confidence=Confidence.HIGH),

        # --- communications -------------------------------------------------
        RelSpec("py_comms", "t_contact", RelationshipType.READS_FROM,
                confidence=Confidence.HIGH,
                evidence=[e("/integrations/comms/comms_digest.py", 17,
                            "SELECT StudentID, Email, Mobile FROM Student.Contact")]),
        RelSpec("py_comms", "api_comms", RelationshipType.CALLS, confidence=Confidence.HIGH),
        RelSpec("api_comms", "comms", RelationshipType.DEPENDS_ON, confidence=Confidence.HIGH),
        RelSpec("job_comms", "py_comms", RelationshipType.RUNS, confidence=Confidence.CONFIRMED),
        RelSpec("job_comms", "batch01", RelationshipType.RUNS_ON, confidence=Confidence.HIGH),
        RelSpec("py_comms", "batch01", RelationshipType.RUNS_ON, confidence=Confidence.HIGH),

        # --- archive / unknown ---------------------------------------------
        RelSpec("job_archive", "dir_archive", RelationshipType.DEPENDS_ON,
                confidence=Confidence.LOW,
                evidence=[e("/etc/cron.d/archive-cleanup", 1,
                            "0 1 * * 0 root /usr/local/bin/archive-cleanup.sh",
                            EvidenceKind.CRON_EXPRESSION)]),
        RelSpec("job_archive", "db2", RelationshipType.RUNS_ON, confidence=Confidence.MEDIUM),
        RelSpec("t_archive", "sch_admin", RelationshipType.DEPENDS_ON, confidence=Confidence.HIGH),
        RelSpec("t_person", "sch_student", RelationshipType.DEPENDS_ON, confidence=Confidence.CONFIRMED),
        RelSpec("t_enrol", "sch_student", RelationshipType.DEPENDS_ON, confidence=Confidence.CONFIRMED),
        RelSpec("t_contact", "sch_student", RelationshipType.DEPENDS_ON, confidence=Confidence.CONFIRMED),
        RelSpec("sch_student", "db_sis", RelationshipType.DEPENDS_ON, confidence=Confidence.CONFIRMED),
        RelSpec("sch_admin", "db_sis", RelationshipType.DEPENDS_ON, confidence=Confidence.CONFIRMED),
        RelSpec("db_sis", "legacysis", RelationshipType.DEPENDS_ON, confidence=Confidence.CONFIRMED),
        RelSpec("db_fin", "finance", RelationshipType.DEPENDS_ON, confidence=Confidence.CONFIRMED),
        RelSpec("sch_finance", "db_fin", RelationshipType.DEPENDS_ON, confidence=Confidence.CONFIRMED),
        RelSpec("t_invoice", "sch_finance", RelationshipType.DEPENDS_ON, confidence=Confidence.CONFIRMED),
        RelSpec("t_ledger", "sch_finance", RelationshipType.DEPENDS_ON, confidence=Confidence.CONFIRMED),
        RelSpec("t_fee", "sch_finance", RelationshipType.DEPENDS_ON, confidence=Confidence.CONFIRMED),
        RelSpec("sch_mart", "reporting", RelationshipType.DEPENDS_ON, confidence=Confidence.CONFIRMED),
        RelSpec("t_dim_student", "sch_mart", RelationshipType.DEPENDS_ON, confidence=Confidence.CONFIRMED),
        RelSpec("t_fact_enrol", "sch_mart", RelationshipType.DEPENDS_ON, confidence=Confidence.CONFIRMED),
        RelSpec("t_fact_fees", "sch_mart", RelationshipType.DEPENDS_ON, confidence=Confidence.CONFIRMED),
        RelSpec("sch_portal", "db_portal", RelationshipType.DEPENDS_ON, confidence=Confidence.CONFIRMED),
        RelSpec("t_applications", "sch_portal", RelationshipType.DEPENDS_ON, confidence=Confidence.CONFIRMED),
        RelSpec("t_applicants", "sch_portal", RelationshipType.DEPENDS_ON, confidence=Confidence.CONFIRMED),
        RelSpec("db_portal", "portal", RelationshipType.DEPENDS_ON, confidence=Confidence.CONFIRMED),

        # --- direct system-level calls --------------------------------------
        # An operator describes this as "the script talks to IdentityHub", so
        # the system itself is linked, not just its API facade. This is what
        # makes the external system show up in impact analysis.
        RelSpec("py_identity", "identity", RelationshipType.CALLS,
                confidence=Confidence.HIGH,
                evidence=[e(ident, 52, "provisions accounts in IdentityHub")]),
        RelSpec("py_enrol", "portal", RelationshipType.CALLS,
                confidence=Confidence.HIGH,
                evidence=[e(enrol, 64, "imports applications into EnrolmentPortal")]),
        RelSpec("ps_learning", "learning", RelationshipType.CALLS,
                confidence=Confidence.MEDIUM,
                evidence=[e("/integrations/learning/learningcloud_export.ps1", 40,
                            "uploads the student export to LearningCloud", EvidenceKind.INFERRED)]),
        RelSpec("py_transport", "transport", RelationshipType.CALLS,
                confidence=Confidence.MEDIUM,
                evidence=[e("/integrations/transport/transport_sync.py", 12,
                            "syncs eligibility to TransportTracker", EvidenceKind.INFERRED)]),
        RelSpec("py_comms", "comms", RelationshipType.CALLS,
                confidence=Confidence.HIGH,
                evidence=[e("/integrations/comms/comms_digest.py", 17,
                            "dispatches via CommsGateway")]),
        RelSpec("ps_hr", "payroll", RelationshipType.CALLS,
                confidence=Confidence.HIGH,
                evidence=[e("/integrations/hr/hr_feed.ps1", 55,
                            "uploads positions to PayrollPlus")]),

        # --- named integrations --------------------------------------------
        RelSpec("int_student_portal", "py_enrol", RelationshipType.RUNS, confidence=Confidence.HIGH),
        RelSpec("int_student_portal", "f_students", RelationshipType.DEPENDS_ON, confidence=Confidence.HIGH),
        RelSpec("int_student_portal", "portal", RelationshipType.DEPENDS_ON, confidence=Confidence.HIGH),
        RelSpec("int_student_identity", "py_identity", RelationshipType.RUNS, confidence=Confidence.HIGH),
        RelSpec("int_student_identity", "f_students", RelationshipType.DEPENDS_ON, confidence=Confidence.HIGH),
        RelSpec("int_student_identity", "identity", RelationshipType.DEPENDS_ON, confidence=Confidence.HIGH),
        RelSpec("int_student_learning", "ps_learning", RelationshipType.RUNS, confidence=Confidence.HIGH),
        RelSpec("int_student_learning", "learning", RelationshipType.DEPENDS_ON, confidence=Confidence.HIGH),
        RelSpec("int_finance_reporting", "py_finance", RelationshipType.RUNS, confidence=Confidence.HIGH),
        RelSpec("int_finance_reporting", "sql_reporting", RelationshipType.RUNS, confidence=Confidence.HIGH),
        RelSpec("int_finance_reporting", "reporting", RelationshipType.DEPENDS_ON, confidence=Confidence.HIGH),
        RelSpec("int_hr_payroll", "ps_hr", RelationshipType.RUNS, confidence=Confidence.HIGH),
        RelSpec("int_hr_payroll", "payroll", RelationshipType.DEPENDS_ON, confidence=Confidence.HIGH),
        RelSpec("int_enrolment_crm", "api_crm", RelationshipType.CALLS, confidence=Confidence.MEDIUM),
        RelSpec("int_enrolment_crm", "portal", RelationshipType.DEPENDS_ON, confidence=Confidence.HIGH),
        RelSpec("int_enrolment_crm", "crm", RelationshipType.DEPENDS_ON, confidence=Confidence.HIGH),
        RelSpec("int_transport", "py_transport", RelationshipType.RUNS, confidence=Confidence.HIGH),
        RelSpec("int_transport", "transport", RelationshipType.DEPENDS_ON, confidence=Confidence.HIGH),
        RelSpec("int_comms", "py_comms", RelationshipType.RUNS, confidence=Confidence.HIGH),
        RelSpec("int_comms", "comms", RelationshipType.DEPENDS_ON, confidence=Confidence.HIGH),
        RelSpec("int_archive", "job_archive", RelationshipType.RUNS, confidence=Confidence.LOW),

        # --- application hosting -------------------------------------------
        RelSpec("hubapp", "app01", RelationshipType.RUNS_ON, confidence=Confidence.HIGH),
        RelSpec("hubapp", "job_student", RelationshipType.TRIGGERS, confidence=Confidence.MEDIUM),
        RelSpec("hubapp", "job_finance", RelationshipType.TRIGGERS, confidence=Confidence.MEDIUM),
        RelSpec("website", "web01", RelationshipType.RUNS_ON, confidence=Confidence.HIGH),
        RelSpec("svcconsole", "legacysis", RelationshipType.CONNECTS_TO, confidence=Confidence.HIGH),
        RelSpec("docs", "f_offers", RelationshipType.IMPORTS_FROM, confidence=Confidence.MEDIUM),
        RelSpec("f_offers", "portal", RelationshipType.PRODUCES, confidence=Confidence.MEDIUM),
        RelSpec("sftp_in", "crm", RelationshipType.IMPORTS_FROM, confidence=Confidence.MEDIUM),
        RelSpec("library", "db2", RelationshipType.CONNECTS_TO, confidence=Confidence.LOW),
        RelSpec("timetable", "legacysis", RelationshipType.READS_FROM, confidence=Confidence.MEDIUM),
    ]


@dataclass
class DemoBundle:
    entities: list[EntitySpec]
    relationships: list[RelSpec]


def build_demo() -> DemoBundle:
    return DemoBundle(entities=list(ENTITY_SPECS), relationships=_build_relationships())


def redacted_snippet(text: str) -> str:
    """Demo evidence is already synthetic, but redact defensively anyway."""
    return redact(text).text
