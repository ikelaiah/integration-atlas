"""nightly_sync.py

Pushes student records into the EnrolmentPortal REST API.
Owner: Digital Team
"""

from __future__ import annotations

import csv

import httpx

IMPORT_URL = "https://enrol.northstar.edu/api/v2/applications/import"
STUDENT_FILE = "/integrations/student/students.csv"


def read_rows() -> list[dict]:
    with open(STUDENT_FILE) as fh:
        return list(csv.DictReader(fh))


def build_payload(rows: list[dict]) -> list[dict]:
    payload = []
    for row in rows:
        payload.append({"student_id": row["StudentID"], "year_level": row["YearLevel"]})
    return payload


def main() -> None:
    rows = read_rows()
    applications = build_payload(rows)
    httpx.post(IMPORT_URL, json={"applications": applications}, timeout=60)


if __name__ == "__main__":
    main()
