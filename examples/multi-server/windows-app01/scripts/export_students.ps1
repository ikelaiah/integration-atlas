# Nightly student export (example bundle artefact).
$conn = 'Server=SHARED-DB-01;Database=LegacySIS;Integrated Security=True'
Invoke-Sqlcmd -ConnectionString $conn -InputFile .\student_extract.sql
Export-Csv -Path \\files01\northstar\outbound\students.csv -NoTypeInformation
