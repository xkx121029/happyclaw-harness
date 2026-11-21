"""Frontmatter splitting for skill and agent manifests."""

from __future__ import annotations

import pytest

from happyclaw_harness.frontmatter import normalize_newlines, split_frontmatter
from happyclaw_harness.skills.catalog import _parse_skill_frontmatter
from happyclaw_harness.subagents.loader import parse_agent_frontmatter

LF_MANIFEST = "---\nname: demo\ndescription: Demo skill\n---\n# Body\n\nText.\n"


def _as_crlf(text: str) -> str:
    return text.replace("\n", "\r\n")


def _as_cr(text: str) -> str:
    return text.replace("\n", "\r")


def test_lf_manifest_is_split() -> None:
    meta, body = split_frontmatter(LF_MANIFEST)
    assert meta == {"name": "demo", "description": "Demo skill"}
    assert body == "# Body\n\nText.\n"


@pytest.mark.parametrize("convert", [_as_crlf, _as_cr], ids=["crlf", "cr"])
def test_windows_line_endings_keep_their_metadata(convert: object) -> None:
    """A CRLF manifest used to lose its frontmatter silently on Windows.

    ``split_frontmatter`` used to require a literal ``---\\n``, so every
    ``SKILL.md`` and agent ``.md`` in a ``core.autocrlf`` checkout or a Windows
    workspace parsed as an empty mapping.
    """
    meta, body = split_frontmatter(convert(LF_MANIFEST))  # type: ignore[operator]
    assert meta == {"name": "demo", "description": "Demo skill"}
    assert body == "# Body\n\nText.\n"


def test_skill_and_agent_parsers_agree_on_crlf() -> None:
    manifest = _as_crlf(LF_MANIFEST)
    assert _parse_skill_frontmatter(manifest) == parse_agent_frontmatter(manifest)
    assert parse_agent_frontmatter(manifest)[0]["name"] == "demo"


@pytest.mark.parametrize(
    "text",
    [
        "",
        "no frontmatter here\n",
        "---\nname: demo\n",
        "---\n- a list\nnot a mapping\n---\nbody\n",
        "---\n\tbroken: [yaml\n---\nbody\n",
    ],
    ids=["empty", "absent", "unterminated", "not-a-mapping", "invalid-yaml"],
)
def test_unusable_frontmatter_returns_the_input_untouched(text: str) -> None:
    assert split_frontmatter(text) == ({}, text)


def test_normalize_newlines_is_idempotent() -> None:
    assert normalize_newlines("a\r\nb\rc\nd") == "a\nb\nc\nd"
    assert normalize_newlines(normalize_newlines("a\r\nb")) == "a\nb"
