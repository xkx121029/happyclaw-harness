"""Click CLI entry point: the `harness` command group."""

from __future__ import annotations

from importlib import import_module
from pathlib import Path

from happyclaw_harness.cli import _check_cli_deps

try:
    _check_cli_deps()
except ImportError as exc:
    raise SystemExit(str(exc)) from None

import click

from happyclaw_harness.cli import __version__, load_dotenv_files

# Subcommand name -> (module, attribute). Each command module pulls the full
# agent stack, so importing them up front made ``--help`` pay for it too.
_COMMAND_SPECS: dict[str, tuple[str, str]] = {
    "agent": ("happyclaw_harness.cli.commands.agent_cmd", "agent"),
    "chat": ("happyclaw_harness.cli.commands.chat", "chat"),
    "config": ("happyclaw_harness.cli.commands.config_cmd", "config"),
    "init": ("happyclaw_harness.cli.commands.init_cmd", "init"),
    "skill": ("happyclaw_harness.cli.commands.skill", "skill"),
    "update": ("happyclaw_harness.cli.commands.update", "update"),
}


class _LazyGroup(click.Group):
    """A group that imports one subcommand only when that subcommand runs."""

    def list_commands(self, ctx: click.Context) -> list[str]:
        return sorted(_COMMAND_SPECS)

    def get_command(self, ctx: click.Context, cmd_name: str) -> click.Command | None:
        spec = _COMMAND_SPECS.get(cmd_name)
        if spec is None:
            return None
        module_name, attr = spec
        command: click.Command = getattr(import_module(module_name), attr)
        return command


@click.group(cls=_LazyGroup, invoke_without_command=True)
@click.version_option(version=__version__, prog_name="happyclaw-harness-cli")
@click.pass_context
def cli(ctx: click.Context) -> None:
    """Harness Agent CLI — chat with AI agents from your terminal."""
    load_dotenv_files(Path.cwd())
    if ctx.invoked_subcommand is None:
        ctx.invoke(cli.get_command(ctx, "chat"))  # type: ignore[arg-type]
