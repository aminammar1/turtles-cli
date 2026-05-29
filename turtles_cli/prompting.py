from __future__ import annotations

from pathlib import Path
import re
import sys
from collections.abc import Callable

from prompt_toolkit import PromptSession
from prompt_toolkit.application import Application
from prompt_toolkit.auto_suggest import AutoSuggestFromHistory
from prompt_toolkit.completion import Completer, Completion
from prompt_toolkit.document import Document
from prompt_toolkit.history import FileHistory
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.layout import HSplit, Layout, VSplit, Window
from prompt_toolkit.widgets import FormattedTextToolbar
from prompt_toolkit.layout.controls import FormattedTextControl
from prompt_toolkit.styles import Style

from .config import TurtlesConfig
from .modes import TurtleMode
from .providers import PROVIDERS
from .session import history_path


COMMANDS = [
    "/login",
    "/logout",
    "/models",
    "/test-model",
    "/test-ai",
    "/provider",
    "/customize-cli",
    "/skills",
    "/subagents",
    "/hooks",
    "/plugins",
    "/init",
    "/docs",
    "/doc",
    "/code-review",
    "/security",
    "/mcp",
    "/mcp-suggestion",
    "/docker",
    "/api",
    "/AI",
    "/github",
    "/suggest-skills",
    "/suggest-plugins",
    "/suggest-subagents",
    "/create-prompt",
    "/enhance-prompt",
    "/prompt-eval",
    "/simulation",
    "/turtle-mode",
    "/help",
    "/ai-detect",
    "/context",
    "/bash",
    "/web-search",
    "/search",
    "/mode",
    "/exit",
    "/quit",
]

COMMAND_DESCRIPTIONS = {
    "/login": "configure provider credentials",
    "/logout": "clear project credentials",
    "/models": "list or switch models",
    "/test-model": "test active model connectivity",
    "/test-ai": "alias for test-model",
    "/provider": "switch provider",
    "/customize-cli": "change CLI display settings",
    "/skills": "manage skills",
    "/subagents": "manage sub-agents",
    "/hooks": "manage lifecycle hooks",
    "/plugins": "manage plugins",
    "/init": "initialize project config",
    "/docs": "create custom instruction file",
    "/doc": "alias for docs",
    "/code-review": "review current project",
    "/security": "scan secrets and risky patterns",
    "/mcp": "manage MCP servers",
    "/mcp-suggestion": "suggest MCP servers",
    "/docker": "audit Docker files",
    "/api": "suggest APIs",
    "/AI": "suggest AI providers/models",
    "/github": "git/GitHub helpers",
    "/suggest-skills": "suggest useful skills",
    "/suggest-plugins": "suggest useful plugins",
    "/suggest-subagents": "suggest useful sub-agents",
    "/create-prompt": "create a prompt",
    "/enhance-prompt": "improve a prompt",
    "/prompt-eval": "score a prompt",
    "/simulation": "grade a scenario",
    "/turtle-mode": "future multi-agent stub",
    "/help": "show help",
    "/ai-detect": "detect AI-generated markers",
    "/context": "show context/cache estimate",
    "/bash": "run shell command",
    "/web-search": "search the web",
    "/search": "alias for web search",
    "/mode": "switch turtle mode",
    "/exit": "exit",
    "/quit": "exit",
}


COLOR_MAP = {
    "blue": "#5aa9ff",
    "purple": "#b48cff",
    "red": "#ff6b6b",
    "orange1": "#ffb454",
    "green": "#67d587",
}

PROJECT_COMPLETION_IGNORES = {".git", ".turtles", ".venv", "__pycache__", "node_modules", "dist", "build"}


class SlashCommandCompleter(Completer):
    def get_completions(self, document: Document, complete_event):
        token = document.get_word_before_cursor(WORD=True)
        before = document.text_before_cursor
        if not token and before.endswith("/"):
            token = "/"
        if not token.startswith("/"):
            return
        if " " in before.strip():
            return

        needle = token.lower()
        bare_needle = needle.lstrip("/")
        for command in COMMANDS:
            lowered = command.lower()
            if lowered.startswith(needle) or lowered.lstrip("/").startswith(bare_needle):
                yield Completion(
                    command,
                    start_position=-len(token),
                    display=command,
                    display_meta=COMMAND_DESCRIPTIONS.get(command, ""),
                )


def project_path_choices(root: Path, *, limit: int = 600) -> list[tuple[str, str]]:
    choices: list[tuple[str, str]] = []
    for path in root.rglob("*"):
        relative_parts = path.relative_to(root).parts
        if any(part in PROJECT_COMPLETION_IGNORES for part in relative_parts):
            continue
        if path.is_dir():
            choices.append((str(path.relative_to(root)) + "/", "directory"))
        elif path.is_file():
            choices.append((str(path.relative_to(root)), "file"))
        if len(choices) >= limit:
            break
    return sorted(choices, key=lambda item: (item[1] != "directory", item[0].lower()))


class ProjectCompleter(Completer):
    def __init__(self, root: Path) -> None:
        self.root = root
        self.slash = SlashCommandCompleter()

    def get_completions(self, document: Document, complete_event):
        yield from self.slash.get_completions(document, complete_event)

        match = re.search(r"@([A-Za-z0-9._/\-]*)$", document.text_before_cursor)
        if not match:
            return
        token = match.group(1)
        needle = token.lower()
        matches: list[tuple[str, str]] = []
        for path, kind in project_path_choices(self.root):
            lowered = path.lower()
            basename = Path(path.rstrip("/")).name.lower()
            if lowered.startswith(needle) or basename.startswith(needle) or needle in lowered:
                matches.append((path, kind))
            if len(matches) >= 30:
                break
        for path, kind in matches:
            yield Completion(
                f"@{path}",
                start_position=-(len(token) + 1),
                display=f"@{path}",
                display_meta=kind,
            )


def project_completion_bindings(*, exit_result: str = "") -> KeyBindings:
    bindings = KeyBindings()

    @bindings.add("c-d")
    def _(event) -> None:
        event.app.exit(result=exit_result)

    @bindings.add("@")
    def _(event) -> None:
        event.current_buffer.insert_text("@")
        event.current_buffer.start_completion(select_first=False)

    @bindings.add("enter")
    def _(event) -> None:
        complete_state = event.current_buffer.complete_state
        if complete_state and complete_state.current_completion:
            event.current_buffer.apply_completion(complete_state.current_completion)
            return
        event.current_buffer.validate_and_handle()

    return bindings


def make_command_session(root: Path, mode: TurtleMode, config: TurtlesConfig) -> PromptSession[str]:
    command_color = COLOR_MAP.get(mode.color, COLOR_MAP["green"])
    provider = PROVIDERS.get(config.provider.provider)
    provider_label = provider.label if provider else "no provider"
    model = config.provider.model or "no model"

    bindings = project_completion_bindings(exit_result="/exit")

    def toolbar() -> str:
        return f"  Tab complete | Up/Down history/menu | ? help | {mode.name} | {provider_label} | {model}"

    return PromptSession(
        completer=ProjectCompleter(root),
        complete_while_typing=True,
        auto_suggest=AutoSuggestFromHistory(),
        history=FileHistory(str(history_path(root))),
        key_bindings=bindings,
        bottom_toolbar=toolbar,
        reserve_space_for_menu=6,
        style=Style.from_dict(
            {
                "prompt": f"bold {command_color}",
                "bottom-toolbar": "bg:#1f1f1f #8a8a8a",
                "completion-menu.completion": "bg:#262626 #d0d0d0",
                "completion-menu.completion.current": f"bg:{command_color} #101010 bold",
                "completion-menu.meta.completion": "bg:#262626 #8a8a8a",
                "scrollbar.background": "bg:#262626",
                "scrollbar.button": f"bg:{command_color}",
            }
        ),
    )


def ask_project_text(root: Path, label: str) -> str:
    if not sys.stdin.isatty() or not sys.stdout.isatty():
        try:
            return input(f"{label}: ").strip()
        except EOFError:
            return ""

    session: PromptSession[str] = PromptSession(
        completer=ProjectCompleter(root),
        complete_while_typing=True,
        key_bindings=project_completion_bindings(),
        bottom_toolbar="  Type @ for project files | Tab complete",
        reserve_space_for_menu=6,
        style=Style.from_dict(
            {
                "completion-menu.completion": "bg:#262626 #d0d0d0",
                "completion-menu.completion.current": "bg:#67d587 #101010 bold",
                "completion-menu.meta.completion": "bg:#262626 #8a8a8a",
                "bottom-toolbar": "bg:#1f1f1f #8a8a8a",
            }
        ),
    )
    return session.prompt(f"{label}: ").strip()


PreviewBuilder = Callable[[str], list[tuple[str, str]]]


def choose_from_keyboard(title: str, choices: list[str], *, default: str, preview: PreviewBuilder | None = None) -> str:
    if not choices:
        return default
    if not sys.stdin.isatty() or not sys.stdout.isatty():
        try:
            answer = input(f"{title} [{default}] > ").strip()
        except EOFError:
            return default
        if not answer:
            return default
        for choice in choices:
            if choice == answer or choice.lower().startswith(answer.lower()):
                return choice
        return default

    selected = choices.index(default) if default in choices else 0
    query = ""
    filtered = list(range(len(choices)))

    def current_choice() -> str:
        return choices[filtered[selected % len(filtered)]] if filtered else default

    def refresh_filter() -> None:
        nonlocal selected, filtered
        needle = query.lower()
        filtered = [index for index, choice in enumerate(choices) if needle in choice.lower()]
        if not filtered:
            filtered = list(range(len(choices)))
        selected = min(selected, len(filtered) - 1)

    def formatted_text():
        lines = [("class:title", f"{title}\n"), ("class:help", "↑/↓ or j/k move · 1-9 jump · type filters · Enter selects · Esc cancels\n\n")]
        if query:
            lines.append(("class:help", f"filter: {query}\n"))
        visible = filtered[:9]
        for row, choice_index in enumerate(visible):
            choice = choices[choice_index]
            pointer = "▶" if row == selected else " "
            style = "class:current" if row == selected else "class:item"
            lines.append((style, f"{pointer} {row + 1}. {choice}\n"))
        return lines

    def preview_text():
        if not preview:
            return []
        return preview(current_choice())

    bindings = KeyBindings()

    @bindings.add("up")
    @bindings.add("k")
    def _(event) -> None:
        nonlocal selected
        selected = (selected - 1) % len(filtered)
        event.app.invalidate()

    @bindings.add("down")
    @bindings.add("j")
    def _(event) -> None:
        nonlocal selected
        selected = (selected + 1) % len(filtered)
        event.app.invalidate()

    @bindings.add("backspace")
    def _(event) -> None:
        nonlocal query
        query = query[:-1]
        refresh_filter()
        event.app.invalidate()

    @bindings.add("enter")
    def _(event) -> None:
        event.app.exit(result=current_choice())

    @bindings.add("escape")
    @bindings.add("c-c")
    def _(event) -> None:
        event.app.exit(result=default)

    for key in [str(number) for number in range(1, 10)]:
        @bindings.add(key)
        def _(event, key=key) -> None:
            nonlocal selected
            index = int(key) - 1
            if index < len(filtered):
                selected = index
                event.app.exit(result=current_choice())

    @bindings.add("<any>")
    def _(event) -> None:
        nonlocal query, selected
        data = event.data
        if data and data.isprintable():
            query += data
            selected = 0
            refresh_filter()
            event.app.invalidate()

    app: Application[str] = Application(
        layout=Layout(
            HSplit(
                [
                    VSplit(
                        [
                            Window(FormattedTextControl(formatted_text), always_hide_cursor=True, width=42),
                            Window(width=2, char=" "),
                            Window(FormattedTextControl(preview_text), always_hide_cursor=True),
                        ]
                    )
                    if preview
                    else Window(FormattedTextControl(formatted_text), always_hide_cursor=True),
                    FormattedTextToolbar(lambda: "Turtles CLI keyboard selector"),
                ]
            )
        ),
        key_bindings=bindings,
        full_screen=False,
        style=Style.from_dict(
            {
                "title": "bold #67d587",
                "help": "#8a8a8a",
                "item": "#d0d0d0",
                "current": "bold #101010 bg:#67d587",
                "preview-title": "bold #67d587",
                "preview-muted": "#8a8a8a",
                "preview-blue": "bold #5aa9ff",
                "preview-purple": "bold #b48cff",
                "preview-red": "bold #ff6b6b",
                "preview-orange": "bold #ffb454",
                "preview-toolbar": "bg:#1f1f1f #8a8a8a",
            }
        ),
    )
    result = app.run()
    return result or default
