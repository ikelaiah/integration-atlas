-- reporting_extract.sql
-- Builds the student dimension and enrolment fact tables for the reporting mart.
-- Owner: Data Platform

INSERT INTO mart.dim_student (StudentID, FirstName, LastName, YearLevel, CampusCode)
SELECT StudentID, FirstName, LastName, YearLevel, CampusCode
FROM Student.Person;

BULK INSERT mart.fact_fees
FROM '/integrations/finance/fee_extract.csv'
WITH (FIELDTERMINATOR = ',', ROWTERMINATOR = '\n');

INSERT INTO mart.fact_enrolment (StudentID, Year, CampusCode)
SELECT StudentID, Year, CampusCode
FROM Student.Enrolment;
