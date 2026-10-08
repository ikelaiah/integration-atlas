"""Shared scanner helpers.

Small, targeted utilities used by more than one scanner. Kept here rather than
in ``base`` so ``base`` stays a pure contract module.
"""

from __future__ import annotations

import re

_ASSIGNMENT = re.compile(
    r"""(?m)^\s*(?:\$)?([A-Za-z_][\w]*)\s*=\s*(?P<q>["'])(?P<value>[^"'\n]{1,400})(?P=q)"""
)


def collect_constants(text: str) -> dict[str, str]:
    """Collect simple ``NAME = "literal"`` bindings for substitution.

    Deliberately shallow: only string literals, only whole-line assignments.
    That is enough to resolve the ``$root = "C:\\integrations"`` and
    ``STUDENT_FILE = "/integrations/..."`` patterns that dominate real
    integration scripts, without pretending to be a language runtime.
    """
    constants: dict[str, str] = {}
    for match in _ASSIGNMENT.finditer(text):
        constants[match.group(1)] = match.group("value")
    return constants


def expand_variables(value: str, constants: dict[str, str]) -> str:
    """Substitute ``$name`` / ``{name}`` / ``%name%`` / bare-word references.

    Quoting context is preserved: a reference that already sits inside a
    string literal is spliced raw, while a bare-word reference is wrapped in
    quotes so downstream path/URL matchers still see a well-formed literal.
    """
    if not constants:
        return value

    def _inside_quote(text: str, index: int) -> bool:
        before = text[max(0, index - 2) : index]
        return bool(before) and before[-1] in "\"'"

    # Sigil forms ($name, ${name}, %name%) always splice raw.
    result = value
    for name, literal in constants.items():
        escaped = re.escape(name)
        result = re.sub(
            rf"\$\{{{escaped}\}}|\${escaped}\b|%{escaped}%",
            lambda _m, lit=literal: lit,
            result,
        )

    # Bare-word references: quote only when not already quoted.
    def _bare(match: re.Match[str]) -> str:
        name = match.group(0)
        literal = constants[name]
        if _inside_quote(result, match.start()):
            return literal
        return f'"{literal}"'

    for name in sorted(constants, key=len, reverse=True):
        result = re.sub(rf"\b{re.escape(name)}\b", _bare, result)

    return result


def join_continuations(text: str, marker: str = "`") -> str:
    """Join PowerShell backtick continuations (and Unix backslash ones).

    Scanners analyse *statements*, not lines; real PowerShell is full of
    multi-line cmdlet invocations that would otherwise be parsed one fragment
    at a time.
    """
    lines = text.splitlines()
    joined: list[str] = []
    buffer = ""
    for line in lines:
        stripped = line.rstrip()
        if stripped.endswith(marker):
            buffer += stripped[:-1] + " "
            continue
        buffer += stripped
        joined.append(buffer)
        buffer = ""
    if buffer:
        joined.append(buffer)
    return "\n".join(joined)


def preserve_line_numbers(original: str, joined: str) -> list[int]:
    """Map each line of ``joined`` back to a line number in ``original``.

    Best-effort: uses prefix matching so line numbers in evidence stay close
    to the truth even after continuations are folded away.
    """
    original_lines = original.splitlines()
    mapping: list[int] = []
    cursor = 0
    for line in joined.splitlines():
        target = line.strip()[:40]
        found = cursor
        for index in range(cursor, len(original_lines)):
            if original_lines[index].strip().startswith(target[:20]) and target:
                found = index
                break
        mapping.append(found + 1)
        cursor = found
    return mapping
