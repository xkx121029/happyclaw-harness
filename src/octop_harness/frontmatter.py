"""YAML frontmatter splitting shared by skill and subagent manifests."""

from __future__ import annotations

from typing import Any

import yaml


def normalize_newlines(text: str) -> str:
    """Collapse CRLF and lone CR to LF so manifests parse the same everywhere."""
    return text.replace("\r\n", "\n").replace("\r", "\n")


def split_frontmatter(text: str) -> tuple[dict[str, Any], str]:
    """Split ``---``-delimited YAML frontmatter from the body.

    Returns ``({}, text)`` when the header is missing, unterminated, not valid
    YAML, or not a mapping. Line endings are normalized first: a Windows
    workspace (or a ``core.autocrlf`` checkout) otherwise never matches the
    opening ``---\\n`` and every skill or agent manifest silently loses its
    metadata.
    """
    normalized = normalize_newlines(text)
    if not normalized.startswith("---\n"):
        return {}, text
    end = normalized.find("\n---", 4)
    if end == -1:
        return {}, text
    raw = normalized[4:end]
    body = normalized[end + 4 :].lstrip("\n")
    try:
        meta = yaml.safe_load(raw) or {}
    except yaml.YAMLError:
        return {}, text
    if not isinstance(meta, dict):
        return {}, text
    return meta, body


__all__ = ["normalize_newlines", "split_frontmatter"]
