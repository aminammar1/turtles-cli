from __future__ import annotations

from pathlib import Path
import sys

from prompt_toolkit import PromptSession
from prompt_toolkit.auto_suggest import AutoSuggestFromHistory
from prompt_toolkit.completion import Completer, Completion, WordCompleter
from prompt_toolkit.document import Document
from prompt_toolkit.history import FileHistory
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.styles import Style

from .config import TurtlesConfig
from .modes import TurtleMode
from .providers import PROVIDERS
from .session import history_path


COMMANDS = [
    "/login",
    "/models",
    "/provider",
    "/customize-cli",
    "/skills",
    "/subagents",
    "/hooks",
    "/plugins",
    "/init",
    "/docs",
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
    "/models": "list or switch models",
    "/provider": "switch provider",
    "/customize-cli": "change CLI display settings",
    "/skills": "manage skills",
    "/subagents": "manage sub-agents",
    "/hooks": "manage lifecycle hooks",
    "/plugins": "manage plugins",
    "/init": "initialize project config",
    "/docs": "generate project rules docs",
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


def make_command_session(root: Path, mode: TurtleMode, config: TurtlesConfig) -> PromptSession[str]:
    command_color = COLOR_MAP.get(mode.color, COLOR_MAP["green"])
    provider = PROVIDERS.get(config.provider.provider)
    provider_label = provider.label if provider else "no provider"
    model = config.provider.model or "no model"

    bindings = KeyBindings()

    @bindings.add("c-d")
    def _(event) -> None:
        event.app.exit(result="/exit")

    def toolbar() -> str:
        return f"  Tab complete | Up/Down history/menu | ? help | {mode.name} | {provider_label} | {model}"

    return PromptSession(
        completer=SlashCommandCompleter(),
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


def choose_from_keyboard(title: str, choices: list[str], *, default: str) -> str:
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

    completer = WordCompleter(choices, ignore_case=True, match_middle=True)
    session: PromptSession[str] = PromptSession(
        completer=completer,
        complete_while_typing=True,
        reserve_space_for_menu=min(8, len(choices) + 1),
        bottom_toolbar="  Type, Tab complete, Enter select",
    )
    answer = session.prompt(f"{title} [{default}] > ").strip()
    if not answer:
        return default
    if answer in choices:
        return answer
    lowered = answer.lower()
    for choice in choices:
        if choice.lower() == lowered or choice.lower().startswith(lowered):
            return choice
    return default
