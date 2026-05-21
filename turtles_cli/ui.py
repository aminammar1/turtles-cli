from __future__ import annotations

import getpass
import sys
import time
from pathlib import Path

from rich import box
from rich.align import Align
from rich.console import Console
from rich.live import Live
from rich.panel import Panel
from rich.prompt import Confirm, Prompt
from rich.table import Table
from rich.text import Text

from .modes import MODES, TurtleMode


console = Console()
UNICODE_OK = (console.encoding or "").lower().replace("-", "") == "utf8"
TURTLE_GLYPH = "🐢" if UNICODE_OK else ""
BULLET = "●" if UNICODE_OK else "*"

WORDMARK = [
    " _______  __   __  ______    _______  ___      _______  _______ ",
    "|_     _||  | |  ||    _ |  |_     _||   |    |       ||       |",
    "  |   |  |  | |  ||   | ||    |   |  |   |    |    ___||  _____|",
    "  |   |  |  |_|  ||   |_||_   |   |  |   |    |   |___ | |_____ ",
    "  |   |  |       ||    __  |  |   |  |   |___ |    ___||_____  |",
    "  |   |  |       ||   |  | |  |   |  |       ||   |___  _____| |",
    "  |___|  |_______||___|  |_|  |___|  |_______||_______||_______|",
]

MASKS = [
    ("LEO", "blue", "strategy"),
    ("DON", "purple", "analysis"),
    ("RPH", "red", "audit"),
    ("MIK", "orange1", "creative"),
]


def animate_startup(enabled: bool = True) -> None:
    if not enabled:
        return
    steps = [
        ("opening sewer channel", 0),
        ("checking project trust", 1),
        ("loading turtle modes", 2),
        ("arming slash commands", 3),
        ("ready", 4),
    ]
    with Live("", console=console, refresh_per_second=12, transient=True) as live:
        for label, active in steps:
            live.update(build_logo(active_mask=active, subtitle=label))
            time.sleep(0.18)
    console.clear()


def build_logo(active_mask: int | None = None, subtitle: str | None = None) -> Table:
    logo = Table.grid(expand=False)
    logo.add_column()
    for line in WORDMARK:
        logo.add_row(Align.center(Text(line, style="bold green")))
    mask_line = Text()
    for index, (name, color, role) in enumerate(MASKS):
        style = f"bold {color}" if active_mask is None or active_mask == index else f"dim {color}"
        mask_line.append(f"  [{name}] ", style=style)
        mask_line.append(role, style="dim")
    logo.add_row(Align.center(mask_line))
    logo.add_row(Align.center(Text("project prep shell  //  prompts  audits  mcp  hooks", style="dim")))
    if subtitle:
        logo.add_row(Align.center(Text(f"> {subtitle}", style="bold green")))
    return logo


def divider() -> None:
    if UNICODE_OK:
        console.rule(style="dim")
    else:
        console.print("[dim]" + ("-" * min(console.width, 80)) + "[/dim]")


def render_header(root: Path, mode: TurtleMode | None = None, provider: str | None = None) -> None:
    title = Text()
    title.append("TURTLES CLI", style="bold green")
    title.append("  v0.1.0", style="dim")
    if mode:
        title.append(f"  //  {mode.name}", style=f"bold {mode.color}")
    details = Text()
    details.append_text(title)
    details.append("\n")
    details.append(str(root), style="dim")
    details.append("\n")
    details.append(f"Provider: {provider or 'not logged in'} | Project prep shell", style="dim")
    if mode:
        details.append("\n")
        details.append(mode.focus, style="dim")
    console.print()
    console.print(build_logo(active_mask=list(MODES).index(mode.key) if mode else None))
    console.print(details)
    divider()


def trust_prompt() -> bool:
    warning = "⚠ " if UNICODE_OK else ""
    return Confirm.ask(f"[bold yellow]{warning}Trust this project folder?[/bold yellow]", default=False)


def choose_mode(default_key: str = "leonardo") -> TurtleMode:
    console.print("[bold]Choose a turtle mode[/bold]")
    console.print("[dim]Use 1-4. Enter keeps the highlighted mode.[/dim]\n")
    short_focus = {
        "leonardo": "planning and balanced review",
        "donatello": "architecture and deep analysis",
        "raphael": "fast audits and blunt feedback",
        "michelangelo": "creative prompts and experiments",
    }
    for index, mode in enumerate(MODES.values(), start=1):
        marker = ">" if mode.key == default_key else " "
        console.print(
            f"[dim]{marker} {index}[/dim] "
            f"[bold {mode.color}]{mode.name:<13}[/bold {mode.color}] "
            f"[dim]{mode.personality:<24}[/dim] {short_focus[mode.key]}"
        )
    console.print()
    default_index = list(MODES).index(default_key) + 1 if default_key in MODES else 1
    answer = console.input("[bold green]> [/bold green]").strip() or str(default_index)
    while answer not in {"1", "2", "3", "4"}:
        console.print("[red]Choose 1, 2, 3, or 4.[/red]")
        answer = console.input("[bold green]> [/bold green]").strip() or str(default_index)
    divider()
    return list(MODES.values())[int(answer) - 1]


def status(message: str, mode: TurtleMode, *, style: str | None = None) -> None:
    console.print(f"[{style or mode.color}]{BULLET}[/{style or mode.color}] {message}")


def shell_problem(message: str) -> None:
    suffix = f" {TURTLE_GLYPH}" if TURTLE_GLYPH else ""
    console.print(f"[bold red]Shell, we have a problem{suffix}[/bold red] [red]{message}[/red]")


def panel(title: str, body: str, mode: TurtleMode, *, border_style: str | None = None) -> None:
    console.print(Panel(body, title=title, border_style=border_style or mode.color, box=box.ROUNDED))


def assistant_message(message: str, mode: TurtleMode) -> None:
    console.print(f"[{mode.color}]{BULLET}[/] {message}")


def shell_footer() -> None:
    console.print("[dim]? for shortcuts                                                Thinking off (tab to toggle)[/dim]")


def masked_prompt(label: str) -> str:
    """Read sensitive input while showing one * per character when possible."""
    console.print(f"{label}: ", end="")
    if sys.platform == "win32":
        try:
            import msvcrt

            chars: list[str] = []
            while True:
                char = msvcrt.getwch()
                if char in {"\r", "\n"}:
                    console.print()
                    return "".join(chars)
                if char == "\003":
                    raise KeyboardInterrupt
                if char == "\b":
                    if chars:
                        chars.pop()
                        console.print("\b \b", end="")
                    continue
                if char in {"\x00", "\xe0"}:
                    msvcrt.getwch()
                    continue
                chars.append(char)
                console.print("*", end="")
        except (ImportError, OSError):
            console.print()
            return getpass.getpass(f"{label}: ")

    try:
        import termios
        import tty

        fd = sys.stdin.fileno()
        old_settings = termios.tcgetattr(fd)
        chars: list[str] = []
        try:
            tty.setraw(fd)
            while True:
                char = sys.stdin.read(1)
                if char in {"\r", "\n"}:
                    console.print()
                    return "".join(chars)
                if char == "\x03":
                    raise KeyboardInterrupt
                if char in {"\x7f", "\b"}:
                    if chars:
                        chars.pop()
                        console.print("\b \b", end="")
                    continue
                chars.append(char)
                console.print("*", end="")
        finally:
            termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)
    except (ImportError, OSError):
        console.print()
        return getpass.getpass(f"{label}: ")
