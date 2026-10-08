-- student_extract.sql
-- Nightly student cohort extract for the enrolment and identity integrations.
-- Owner: Integration Team

SELECT
    s.StudentID,
    s.FirstName,
    s.LastName,
    s.DateOfBirth,
    s.YearLevel,
    s.CampusCode
FROM Student.Person s
JOIN Student.Enrolment e
    ON e.StudentID = s.StudentID
   AND e.Year = 2026
WHERE s.YearLevel BETWEEN 0 AND 12
  AND s.ExitDate IS NULL;
