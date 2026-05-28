from __future__ import annotations

import getpass
import sys
import threading
import time
from contextlib import contextmanager
from pathlib import Path
from collections.abc import Iterator

from rich import box
from rich.align import Align
from rich.console import Console
from rich.live import Live
from rich.markdown import Markdown
from rich.panel import Panel
from rich.prompt import Confirm, Prompt
from rich.table import Table
from rich.text import Text

from .mascots import mascot_frame, mascot_rich_lines
from .modes import MODES, TurtleMode


console = Console()
UNICODE_OK = (console.encoding or "").lower().replace("-", "") == "utf8"
TURTLE_GLYPH = "🐢" if UNICODE_OK else ""
BULLET = "●" if UNICODE_OK else "*"

WORDMARK = [
    "████████╗██╗   ██╗██████╗ ████████╗██╗     ███████╗███████╗",
    "╚══██╔══╝██║   ██║██╔══██╗╚══██╔══╝██║     ██╔════╝██╔════╝",
    "   ██║   ██║   ██║██████╔╝   ██║   ██║     █████╗  ███████╗",
    "   ██║   ██║   ██║██╔══██╗   ██║   ██║     ██╔══╝  ╚════██║",
    "   ██║   ╚██████╔╝██║  ██║   ██║   ███████╗███████╗███████║",
    "   ╚═╝    ╚═════╝ ╚═╝  ╚═╝   ╚═╝   ╚══════╝╚══════╝╚══════╝",
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


def build_mascot(mode: TurtleMode, frame: int = 0, activity: str = "idle") -> Table:
    mascot = Table.grid(expand=False)
    mascot.add_column()
    for text_line in mascot_rich_lines(mode, frame, activity):
        mascot.add_row(Align.center(text_line))
    mascot.add_row(Align.center(Text(mode.name, style=f"bold {mode.color}")))
    mascot.add_row(Align.center(Text(mode.focus, style="dim")))
    return mascot


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
    if mode:
        header = Table.grid(expand=False)
        header.add_column()
        header.add_column()
        header.add_row(build_logo(active_mask=list(MODES).index(mode.key)), build_mascot(mode))
        console.print(header)
    else:
        console.print(build_logo())
    console.print(details)
    divider()


def trust_prompt() -> bool:
    warning = "⚠ " if UNICODE_OK else ""
    return Confirm.ask(f"[bold yellow]{warning}Trust this project folder?[/bold yellow]", default=False)


def choose_mode(default_key: str = "leonardo") -> TurtleMode:
    from .prompting import choose_from_keyboard

    short_focus = {
        "leonardo": "planning and balanced review",
        "donatello": "architecture and deep analysis",
        "raphael": "fast audits and blunt feedback",
        "michelangelo": "creative prompts and experiments",
    }
    labels = [f"{mode.name} - {mode.personality}; {short_focus[mode.key]}" for mode in MODES.values()]
    default_mode = MODES.get(default_key, next(iter(MODES.values())))
    default_label = next(label for label in labels if label.startswith(default_mode.name))
    answer = choose_from_keyboard("Choose turtle mode", labels, default=default_label)
    divider()
    selected_name = answer.split(" - ", 1)[0]
    return next((mode for mode in MODES.values() if mode.name == selected_name), default_mode)


def status(message: str, mode: TurtleMode, *, style: str | None = None) -> None:
    console.print(f"[{style or mode.color}]{BULLET}[/{style or mode.color}] {message}")


def shell_problem(message: str) -> None:
    suffix = f" {TURTLE_GLYPH}" if TURTLE_GLYPH else ""
    error = Text()
    error.append("✖ " if UNICODE_OK else "x ", style="bold red")
    error.append(message, style="red")
    console.print(Panel(error, title=f"[bold red]Error{suffix}[/bold red]", border_style="red", box=box.HEAVY))


def panel(title: str, body: str, mode: TurtleMode, *, border_style: str | None = None) -> None:
    console.print(Panel(body, title=title, border_style=border_style or mode.color, box=box.ROUNDED))


def markdown_panel(title: str, body: str, mode: TurtleMode, *, border_style: str | None = None) -> None:
    console.print(Panel(Markdown(body), title=title, border_style=border_style or mode.color, box=box.ROUNDED))


def assistant_message(message: str, mode: TurtleMode) -> None:
    console.print(f"[{mode.color}]{BULLET}[/] {message}")


def shell_footer() -> None:
    console.print("[dim]? for shortcuts                                                Thinking off (tab to toggle)[/dim]")


@contextmanager
def processing_animation(message: str, mode: TurtleMode, *, phases: list[str] | None = None, min_duration: float = 0.75) -> Iterator[None]:
    stop = threading.Event()
    started = time.monotonic()
    with Live("", console=console, refresh_per_second=10, transient=False) as live:
        def run() -> None:
            frame = 0
            steps = phases or ["reading project", "running tool", "collecting output", "rendering result"]
            spinner = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"] if UNICODE_OK else ["-", "\\", "|", "/"]
            while not stop.is_set():
                elapsed = time.monotonic() - started
                active = steps[frame % len(steps)]
                body = Table.grid(expand=False)
                body.add_column()
                body.add_row(Text(f"> {message} is running...", style=f"bold {mode.color}"))
                for phase in steps:
                    marker = spinner[frame % len(spinner)] if phase == active else "·"
                    style = f"bold {mode.color}" if phase == active else "dim"
                    prefix = "│" if phase == active else " "
                    body.add_row(Text(f"{prefix} {marker} {phase}", style=style))
                body.add_row(Text(f"└ elapsed {elapsed:0.1f}s", style="dim"))
                live.update(body)
                frame += 1
                time.sleep(0.16)

        thread = threading.Thread(target=run, daemon=True)
        thread.start()
        try:
            yield
        finally:
            remaining = min_duration - (time.monotonic() - started)
            if remaining > 0:
                time.sleep(remaining)
            stop.set()
            thread.join(timeout=0.5)
            elapsed = time.monotonic() - started
            done = Table.grid(expand=False)
            done.add_column()
            done.add_row(Text(f"> {message} completed in {elapsed:0.1f}s", style=f"bold {mode.color}"))
            live.update(done)


def render_context_usage(usage: dict[str, object], mode: TurtleMode) -> None:
    categories = usage.get("categories", {})
    if not isinstance(categories, dict):
        categories = {}
    used = int(usage.get("used", 0))
    window = max(1, int(usage.get("window", 1)))
    percent = round((used / window) * 100)
    filled = min(20, round((used / window) * 20))
    bar = "▣" * filled + "▢" * (20 - filled)

    table = Table.grid(expand=False)
    table.add_column()
    table.add_column()
    table.add_row(Text("╰─ Context Usage", style=f"bold {mode.color}"), Text(f"{usage.get('model', 'model')} · {used/1000:.0f}k/{window/1000:.0f}k tokens ({percent}%)", style="dim"))
    table.add_row(Text(bar, style=f"bold {mode.color}"), Text(""))
    table.add_row("", Text("Estimated usage by category", style="italic dim"))
    for name, value in categories.items():
        tokens = int(value)
        label = name.replace("_", " ").title()
        table.add_row("", Text(f"◉ {label}: {tokens/1000:.1f}k tokens ({(tokens / window) * 100:.1f}%)", style="dim"))
    table.add_row("", Text(f"□ Free space: {int(usage.get('remaining', 0))/1000:.0f}k tokens ({(int(usage.get('remaining', 0)) / window) * 100:.1f}%)", style="green"))
    table.add_row("", Text(f"▧ Autocompact buffer: {int(usage.get('autocompact_buffer', 0))/1000:.0f}k tokens ({(int(usage.get('autocompact_buffer', 0)) / window) * 100:.1f}%)", style="dim"))
    console.print(table)


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
