"""Harness Agent CLI — terminal interface.

Install with: pip install happyclaw-harness[cli]
"""

from __future__ import annotations

from importlib.util import find_spec
from pathlib import Path

from happyclaw_harness._version import __version__


def _check_cli_deps() -> None:
    """Raise ImportError if CLI dependencies are missing.

    Uses ImportError (not SystemExit) so importing ``happyclaw_harness.cli.main``
    during test collection cannot abort the whole pytest session.
    The CLI entrypoint converts this into a friendly ``SystemExit``.

    ``find_spec`` proves presence without executing the module: importing
    ``rich`` and ``prompt_toolkit`` here cost ~170 modules on every
    ``happyclaw-harness --help``.
    """
    missing = [mod for mod in ("click", "rich", "prompt_toolkit", "dotenv") if find_spec(mod) is None]
    if missing:
        raise ImportError(
            f"Missing CLI dependencies: {', '.join(missing)}.\nInstall them with: pip install happyclaw-harness[cli]"
        )


def load_dotenv_files(project_dir: Path, *, override: bool = False) -> Path | None:
    """Load the first .env file found (project dir → global ~/.octop-harness/).

    Args:
        project_dir: The current working directory to check for a project .env.
        override: If True, overwrite existing env vars (reload semantics).
                  If False (default), existing env vars take precedence.

    Returns:
        The Path of the .env file that was loaded, or None if none found.
    """
    from dotenv import load_dotenv

    candidates = [
        project_dir / ".env",
        Path.home() / ".octop-harness" / ".env",
    ]
    for path in candidates:
        if path.is_file():
            load_dotenv(path, override=override)
            return path
    return None


__all__ = ["__version__", "_check_cli_deps", "load_dotenv_files"]
