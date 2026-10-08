# Identity sync (example bundle artefact).
import requests

requests.get("https://identity.northstar.example/scim/v2/Users")
with open("/data/enrolment/students.csv") as handle:
    handle.read()
