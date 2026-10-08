"""identity_sync.py

Reads the nightly student extract and provisions accounts in IdentityHub.
Owner: Identity Team
"""

from __future__ import annotations

import logging
import os

import pandas as pd
import requests

log = logging.getLogger(__name__)

STUDENT_FILE = "/integrations/student/students.csv"
SCIM_URL = "https://identity.northstar.edu/scim/v2/Users"


def load_students() -> pd.DataFrame:
    return pd.read_csv(STUDENT_FILE, dtype={"StudentID": str})


def provision(row) -> dict:
    user_name = f"{row.StudentID}@northstar.edu"
    return {
        "userName": user_name,
        "name": {"givenName": row.FirstName, "familyName": row.LastName},
        "active": True,
    }


def push(students: pd.DataFrame) -> None:
    token = os.environ.get("IDENTITY_HUB_TOKEN", "")
    for _, row in students.iterrows():
        payload = provision(row)
        requests.post(
            SCIM_URL,
            headers={"Authorization": f"Bearer {token}"},
            json=payload,
            timeout=30,
        )


if __name__ == "__main__":
    push(load_students())
