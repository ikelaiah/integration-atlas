"""Secret detection and redaction.

This module is the single choke point for sensitive values. Scanners call
:func:`redact` on every snippet *before* it can reach an Evidence row, a log
line or an API response.

Design rules:

* Nothing here ever returns or stores the original secret.
* Detection is deliberately over-eager: a false positive costs a few
  characters of context, a false negative leaks a credential.
* Redaction is stable and reversible only in the sense that the *shape* of the
  value is preserved (``Password=<redacted:password>``) so that operators can
  still tell what kind of credential was present.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Final

REDACTED: Final[str] = "<redacted>"
REDACTED_MASK: Final[str] = "<redacted:{kind}>"


@dataclass(frozen=True)
class SecretMatch:
    kind: str
    start: int
    end: int
    preview: str


@dataclass
class RedactionResult:
    text: str
    matches: list[SecretMatch] = field(default_factory=list)

    @property
    def count(self) -> int:
        return len(self.matches)


# --------------------------------------------------------------------------- #
# Patterns
# --------------------------------------------------------------------------- #
# Each entry: (kind, regex over the *whole* assignment-ish span, group index of
# the secret itself, group index of the *key* that owns it — or ``None`` when
# the pattern is keyless and must never be suppressed by the allowlist).
#
# The owning key matters: an allowlisted key must only excuse *its own*
# assignment. A nearby-but-unrelated allowlisted key (``token_type``) must not
# hide a real secret on the next line (``password=...``).
_PATTERNS: Final[list[tuple[str, re.Pattern[str], int, int | None]]] = [
    # key = "value"  /  key: value  /  key value  (quoted or bare)
    (
        "credential",
        re.compile(
            r"""(?ix)
            (?<!\w)
            ["']?
            (
                password|passwd|pwd|passphrase|
                secret|client_secret|clientsecret|
                api[_-]?key|apikey|access[_-]?key|accesskey|
                auth[_-]?token|accesstoken|bearer|token|
                private[_-]?key|privkey|
                credential|credentials|
                sas[_-]?signature|sharedaccesskey
            )
            ["']?
            [ \t]*[:=][ \t]*
            (
                "(?:[^"\\]|\\.)*" |
                '(?:[^'\\]|\\.)*' |
                [^\s,;&"'()\[\]{}]+
            )
            """,
            re.VERBOSE,
        ),
        2,
        1,
    ),
    # Connection-string style password=... (also covered above, but this
    # catches values without a recognised key name following a semicolon).
    # The optional quotes let it read JSON-style ``"password": "..."`` too.
    (
        "connection_string_password",
        re.compile(r"(?i)(?<!\w)[\"']?(password|pwd)[\"']?[ \t]*[:=][ \t]*([^\s;\"']+|\"[^\"]*\"|'[^']*')"),
        2,
        1,
    ),
    # AWS access key id
    ("aws_access_key", re.compile(r"\b(AKIA[0-9A-Z]{16})\b"), 1, None),
    # JWT
    (
        "jwt",
        re.compile(
            r"\b(eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{5,})\b"
        ),
        1,
        None,
    ),
    # Generic bearer tokens in headers
    (
        "bearer_token",
        re.compile(r"(?i)\b(bearer[ \t]+)([A-Za-z0-9._\-]{12,})"),
        2,
        None,
    ),
    # Private key blocks
    (
        "private_key",
        re.compile(
            r"-----BEGIN [A-Z ]*PRIVATE KEY-----[\s\S]*?-----END [A-Z ]*PRIVATE KEY-----"
        ),
        0,
        None,
    ),
    # URL userinfo:  scheme://user:password@host. Embedded credentials are
    # unambiguous, so the allowlist never suppresses them.
    (
        "url_credentials",
        re.compile(r"(?i)(://[^/\s:@]+:)([^/\s@]+)(@)"),
        2,
        None,
    ),
    # Scheme-less userinfo: ``user:password@host`` (e.g. a bare name field or
    # a connection token without a ``scheme://``). An email address has no
    # colon, so this does not fire on ordinary addresses.
    (
        "userinfo_credentials",
        re.compile(r"(?<![\w:/])([^/\s:@]{1,64}):([^/\s@:]{4,})@([A-Za-z0-9][A-Za-z0-9.\-]*)"),
        2,
        None,
    ),
    # ODBC / ADO connection strings with Password or Pwd
    (
        "odbc_password",
        re.compile(r"(?i)(?<!\w)[\"']?(?:password|pwd)[\"']?[ \t]*=[ \t]*([^;\"'\r\n]{1,200})\s*(?:;|$)"),
        1,
        None,
    ),
]

#: Keys that look like secrets but are safe (and useful) to keep.
ALLOWLIST_KEYS: Final[frozenset[str]] = frozenset(
    {
        "password_expires",
        "password_policy",
        "password_length",
        "token_type",
        "token_url",
        "auth_url",
        "secret_name",
        "key_name",
        "key_file",
        "key_path",
        "private_key_path",
        "certificate",
        "thumbprint",
    }
)

def _is_placeholder(value: str) -> bool:
    """Values that are obviously not real credentials."""
    lowered = value.strip().lower()
    if lowered in {"redacted", "<redacted>", "none", "null", "true", "false", "changeme", "todo", "tbd", "xxx"}:
        return True
    if lowered.startswith("<") and lowered.endswith(">"):
        return True
    # Templating artefacts: ${VAR}, %(name)s, {{var}}, $VAR, %VAR%
    return bool(
        re.fullmatch(r"\$\{[^}]+\}|\$\w+|%[({][^)}]+[)}]%?|{{[^}]+}}|\{\{[^}]+\}\}", value.strip())
    )


def _is_allowlisted_key(key: str | None) -> bool:
    """True when *this* assignment's key is an explicitly safe one.

    Only the key that owns the matched value is consulted — never a nearby
    key on another line or another assignment.
    """
    if not key:
        return False
    return key.strip().lower() in ALLOWLIST_KEYS


def find_secrets(text: str) -> list[SecretMatch]:
    """Return every secret occurrence in ``text`` without the secret value."""
    if not text:
        return []
    found: list[SecretMatch] = []
    occupied: list[tuple[int, int]] = []

    for kind, pattern, group, key_group in _PATTERNS:
        for m in pattern.finditer(text):
            if group >= len(m.groups()) + 1:
                continue
            span = m.span(group)
            value = m.group(group)
            if not value or len(value) < 4:
                continue
            if _is_placeholder(value):
                continue
            if key_group is not None and _is_allowlisted_key(m.group(key_group)):
                continue
            if any(not (span[1] <= a or span[0] >= b) for a, b in occupied):
                continue
            occupied.append(span)
            found.append(SecretMatch(kind=kind, start=span[0], end=span[1], preview=""))

    found.sort(key=lambda s: s.start)
    return found


def redact(text: str) -> RedactionResult:
    """Return ``text`` with every secret replaced by a stable mask.

    The result is safe to persist, log and display.
    """
    if not text:
        return RedactionResult(text="", matches=[])
    matches = find_secrets(text)
    if not matches:
        return RedactionResult(text=text, matches=[])

    parts: list[str] = []
    cursor = 0
    for match in matches:
        parts.append(text[cursor : match.start])
        parts.append(REDACTED_MASK.format(kind=match.kind))
        cursor = match.end
    parts.append(text[cursor:])
    return RedactionResult(text="".join(parts), matches=matches)


def redact_mapping(data: dict[str, object]) -> tuple[dict[str, object], list[SecretMatch]]:
    """Redact secret-looking values in a flat mapping (config files)."""
    matches: list[SecretMatch] = []
    out: dict[str, object] = {}
    for key, value in data.items():
        if isinstance(value, str):
            result = redact(f"{key}={value}")
            # ``redact`` sees "key=value"; strip the key back off.
            prefix = f"{key}="
            cleaned = result.text[len(prefix) :] if result.text.startswith(prefix) else result.text
            out[key] = cleaned
            matches.extend(result.matches)
        elif isinstance(value, dict):
            nested, nested_matches = redact_mapping(value)  # type: ignore[arg-type]
            out[key] = nested
            matches.extend(nested_matches)
        elif isinstance(value, list):
            cleaned_list: list[object] = []
            for item in value:
                if isinstance(item, str):
                    # Evaluate list items in the context of their key so that
                    # ``tokens: ["s3cr3t-value-here"]`` is still caught.
                    result = redact(f"{key}={item}")
                    prefix = f"{key}="
                    cleaned_item = (
                        result.text[len(prefix) :] if result.text.startswith(prefix) else result.text
                    )
                    cleaned_list.append(cleaned_item)
                    matches.extend(result.matches)
                elif isinstance(item, dict):
                    nested, nested_matches = redact_mapping(item)
                    cleaned_list.append(nested)
                    matches.extend(nested_matches)
                else:
                    cleaned_list.append(item)
            out[key] = cleaned_list
        else:
            out[key] = value
    return out, matches


def redact_value(value: object, key: str | None = None) -> object:
    """Recursively redact every string inside a JSON-like value.

    Used for metadata (``meta_json``) and any other structured payload that
    reaches persistence. Passing the surrounding ``key`` down keeps detection
    as strong as it is for flat config: ``{"api_key": "<secret>"}`` is masked
    just as ``api_key=<secret>`` is. Mapping keys and non-string scalars pass
    through untouched.
    """
    if isinstance(value, str):
        if key:
            result = redact(f"{key}={value}")
            prefix = f"{key}="
            return result.text[len(prefix):] if result.text.startswith(prefix) else result.text
        return redact(value).text
    if isinstance(value, dict):
        return {k: redact_value(v, str(k)) for k, v in value.items()}
    if isinstance(value, list):
        return [redact_value(item, key) for item in value]
    return value


def looks_like_secret(value: str) -> bool:
    """Cheap predicate used by scanners to decide whether to flag a value."""
    return bool(find_secrets(f"value={value}"))
