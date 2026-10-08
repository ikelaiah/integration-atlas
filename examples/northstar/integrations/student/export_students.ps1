# export_students.ps1
# Runs the student extract and writes students.csv to the shared drop folder.
# Owner: Integration Team

$ErrorActionPreference = "Stop"
$root = "C:\integrations\student"

# Connection details are supplied by the scheduled task, not hard-coded here.
Invoke-Sqlcmd -ServerInstance DB2-LEGACY-01 `
    -Database LegacySIS `
    -InputFile "$root\student_extract.sql" `
    -OutputFile "$root\students.csv"

# Drop a copy for the LMS export job to pick up.
Copy-Item -Path "$root\students.csv" `
    -Destination "\\APP-SERVER-01\integrations$\student\students.csv" `
    -Force

Get-Content "$root\students.csv" | Measure-Object -Line
