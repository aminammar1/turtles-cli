from __future__ import annotations

from pathlib import Path
import sys

import typer

from .commands import dispatch, handle_help
from .config import TurtlesConfig, config_path, load_config, save_config
from .modes import get_mode
from .prompting import make_command_session
from .providers import PROVIDERS
from .session import record_command
from .ui import animate_startup, assistant_message, choose_mode, console, divider, render_header, shell_footer, trust_prompt

app = typer.Typer(
    add_completion=False,
    invoke_without_command=True,
    help="Turtles CLI: project prep, audits, MCP, prompts, and workflow optimization.",
)


@app.callback()
def main(
    ctx: typer.Context,
    no_animation: bool = typer.Option(False, "--no-animation", help="Skip the startup turtle animation."),
    command: str | None = typer.Argument(None, help="Optional slash command to run once, for example /help."),
) -> None:
    if ctx.invoked_subcommand is not None:
        return
    root = Path.cwd().resolve()
    first_run = not config_path(root).exists()
    config = load_config(root)
    if command:
        command = command if command.startswith("/") else f"/{command}"
        _, updated = dispatch(command, root, config)
        if updated is not config:
            save_config(updated, root)
        return
    start_shell(root, config, no_animation=no_animation, first_run=first_run)


def start_shell(root: Path, config: TurtlesConfig, *, no_animation: bool = False, first_run: bool = False) -> None:
    animate_startup(enabled=config.display.show_animation and not no_animation)
    if not config.trusted:
        provider = PROVIDERS.get(config.provider.provider)
        render_header(root, provider=provider.label if provider else None)
        if not trust_prompt():
            console.print("[dim]Project not trusted. Exiting cleanly.[/dim]")
            raise typer.Exit(0)
        config.trusted = True
        save_config(config, root)
    if first_run:
        selected_mode = choose_mode(config.mode)
        config.mode = selected_mode.key
        save_config(config, root)
    else:
        selected_mode = get_mode(config.mode)
    console.clear()
    provider = PROVIDERS.get(config.provider.provider)
    render_header(root, selected_mode, provider.label if provider else None)
    resume = "Resumed" if not first_run else "Started"
    auth = f"{provider.label} / {config.provider.model}" if provider and config.provider.model else "not logged in"
    assistant_message(f"{resume} {selected_mode.name} mode. Auth: {auth}. Type /help, /login, /mode, or a slash command.", selected_mode)
    divider()
    while True:
        mode = get_mode(config.mode)
        try:
            if sys.stdin.isatty() and sys.stdout.isatty():
                line = make_command_session(root, mode, config).prompt([("class:prompt", "> ")])
            else:
                line = console.input(f"[bold {mode.color}]> [/bold {mode.color}]")
        except EOFError:
            console.print()
            break
        if line.strip() == "?":
            handle_help([], root, config)
            shell_footer()
            continue
        record_command(root, line, mode=config.mode, provider=config.provider.provider, model=config.provider.model)
        should_continue, config = dispatch(line, root, config)
        if not should_continue:
            console.print("[green]Cowabunga. See you next prep session.[/green]")
            break
        shell_footer()


@app.command("help")
def help_command() -> None:
    handle_help([], Path.cwd().resolve(), load_config())


if __name__ == "__main__":
    app()
