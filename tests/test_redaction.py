"""Tests for the secret-redaction layer.

These are security tests: they assert that no raw secret can survive
:func:`atlas.services.redaction.redact` in any form.
"""

from __future__ import annotations

import pytest

from atlas.services.redaction import REDACTED_MASK, find_secrets, redact, redact_mapping

SECRETS = [
    "SuperSecret123!",
    "hunter2-hunter2-hunter2",
    "AKIAIOSFODNN7EXAMPLE",
    "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIiwibmFtZSI6IkpvaG4ifQ.SflKxwRJSMeKKF2QT4fwpMeJf36POk6yJV_adQssw5c",
    "aGVsbG8td29ybGQtc2VjcmV0LXZhbHVl",
]


@pytest.mark.parametrize("secret", SECRETS)
def test_password_assignment_is_redacted(secret: str) -> None:
    text = f'Server=sql01;Database=students;User=sa;Password="{secret}";'
    result = redact(text)
    assert secret not in result.text
    assert result.count >= 1
    assert "Password=" in result.text
    assert REDACTED_MASK.format(kind="credential") in result.text or "<redacted" in result.text


@pytest.mark.parametrize("secret", SECRETS)
def test_api_key_assignment_is_redacted(secret: str) -> None:
    text = f"API_KEY={secret}\nother=keepme"
    result = redact(text)
    assert secret not in result.text
    assert "keepme" in result.text


@pytest.mark.parametrize("secret", SECRETS)
def test_secret_never_appears_in_match_preview(secret: str) -> None:
    text = f"token: {secret}"
    result = redact(text)
    for match in result.matches:
        assert secret not in match.preview
    assert secret not in result.text


def test_jwt_is_redacted_even_without_a_key_name() -> None:
    jwt = (
        "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9."
        "eyJzdWIiOiIxMjM0NTY3ODkwIiwibmFtZSI6IkpvaG4ifQ."
        "SflKxwRJSMeKKF2QT4fwpMeJf36POk6yJV_adQssw5c"
    )
    result = redact(f"Authorization header carried {jwt} verbatim")
    assert jwt not in result.text


def test_aws_access_key_is_redacted() -> None:
    result = redact("aws_access_key_id=AKIAIOSFODNN7EXAMPLE")
    assert "AKIAIOSFODNN7EXAMPLE" not in result.text


def test_url_userinfo_is_redacted() -> None:
    raw = "postgres://admin:S3cretPass@db.internal:5432/students"
    result = redact(raw)
    assert "S3cretPass" not in result.text
    assert "admin" in result.text
    assert "db.internal:5432/students" in result.text


def test_private_key_block_is_redacted() -> None:
    block = (
        "-----BEGIN RSA PRIVATE KEY-----\n"
        "MIIEpAIBAAKCAQEA0Z3VS5JJcds3xfn/ygWyF0k5\n"
        "-----END RSA PRIVATE KEY-----"
    )
    result = redact(f"key material follows\n{block}\ndone")
    assert "MIIEpAIBAAKCAQEA0Z3VS5JJcds3xfn/ygWyF0k5" not in result.text
    assert "done" in result.text


def test_bearer_token_is_redacted() -> None:
    result = redact("Authorization: Bearer abcdef1234567890abcd")
    assert "abcdef1234567890abcd" not in result.text


def test_allowlisted_keys_are_kept() -> None:
    text = "password_policy=complexity\nkey_file=/etc/certs/app.pem\ntoken_type=Bearer"
    result = redact(text)
    assert "complexity" in result.text
    assert "/etc/certs/app.pem" in result.text
    assert "Bearer" in result.text


def test_placeholders_are_not_treated_as_secrets() -> None:
    text = "Password=<redacted>\napi_key=${API_KEY}\nsecret=none"
    result = redact(text)
    assert result.count == 0
    assert result.text == text


def test_short_values_are_ignored() -> None:
    text = "token=abc"
    result = redact(text)
    assert result.count == 0


def test_redaction_is_idempotent() -> None:
    text = "password=VeryLongSecretValue999"
    once = redact(text)
    twice = redact(once.text)
    assert twice.count == 0
    assert twice.text == once.text


def test_redact_mapping_handles_nested_structures() -> None:
    jwt = (
        "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9."
        "eyJzdWIiOiIxMjM0NTY3ODkwIn0."
        "SflKxwRJSMeKKF2QT4fwpMeJf36POk6yJV_adQssw5c"
    )
    data = {
        "database": {"host": "sql01", "password": "NestedSecretValue123"},
        "api_key": "TopLevelSecretValue456",
        "retries": 3,
        "tags": ["keep-this-tag", jwt],
    }
    cleaned, matches = redact_mapping(data)
    blob = repr(cleaned)
    assert "NestedSecretValue123" not in blob
    assert "TopLevelSecretValue456" not in blob
    assert jwt not in blob
    assert "keep-this-tag" in blob
    assert cleaned["retries"] == 3
    assert cleaned["database"]["host"] == "sql01"  # type: ignore[index]
    assert len(matches) >= 3


def test_overlapping_patterns_do_not_double_report() -> None:
    text = "password=OverlapSecretValue123;"
    matches = find_secrets(text)
    assert len(matches) == 1


def test_no_secret_survives_a_realistic_config_file() -> None:
    config = """
    [connection]
    server = SQL-PROD-01
    database = FinancePro
    user = svc_finance
    password = ProdFinance!2024x

    [api]
    base_url = https://api.example.com/v1
    api_key = api-test-key-do-not-use
    timeout = 30
    """
    result = redact(config)
    assert "ProdFinance!2024x" not in result.text
    assert "api-test-key-do-not-use" not in result.text
    assert "SQL-PROD-01" in result.text
    assert "https://api.example.com/v1" in result.text
    assert result.count >= 2
