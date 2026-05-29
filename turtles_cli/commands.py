from __future__ import annotations

import html
import os
import re
import shlex
import shutil
import subprocess
import urllib.parse
from collections.abc import Callable
from pathlib import Path

import httpx
from rich import box
from rich.prompt import Confirm, Prompt
from rich.table import Table

from .audits import Finding, ai_detect, code_review, context_usage, docker_audit, iter_project_files, safe_read, security_audit
from .config import ProviderConfig, TurtlesConfig, config_dir, init_project, is_logged_in, load_config, save_config
from .llm import LLMError, complete_text, provider_ready
from .modes import TurtleMode, get_mode
from .prompting import ask_project_text, choose_from_keyboard
from .providers import PROVIDERS
from .scaffold import create_plugin, create_skill, create_subagent
from .session import load_cache, save_cache
from .ui import (
    choose_mode,
    command_pick_animation,
    console,
    markdown_panel,
    masked_prompt,
    panel,
    processing_animation,
    render_context_usage,
    shell_problem,
    status,
)


CommandHandler = Callable[[list[str], Path, TurtlesConfig], TurtlesConfig]
MAX_TOOL_OUTPUT = 12_000
MAX_PROJECT_READ_CHARS = 22_000
MAX_PROJECT_READ_FILES = 18
INSTRUCTION_FILES = (
    "TURTLE.md",
    "AGENTS.md",
    "CLAUDE.md",
    "GEMINI.md",
    ".cursorrules",
    ".cursor/rules",
    ".github/copilot-instructions.md",
)
MENTION_RE = re.compile(r"(?<!\w)@([A-Za-z0-9._][A-Za-z0-9._/\-]*)")
FAKE_TOOL_RE = re.compile(
    r"(?is)<\s*tool_(?:call|use)[^>]*>.*?(?:</\s*tool_(?:call|use)\s*>)?|"
    r"\b(?:bash|shell)\s+(?:execute|tool|command)\s*:",
)
FENCED_CODE_RE = re.compile(r"```")
JSON_OBJECT_RE = re.compile(r"^\s*[\[{].*[\]}]\s*$", re.S)


def require_login(config: TurtlesConfig) -> bool:
    if is_logged_in(config):
        return True
    console.print("[yellow]Run /login first. Provider-backed commands unlock after project-scoped credentials are configured.[/yellow]")
    return False


def require_ai(config: TurtlesConfig) -> bool:
    if provider_ready(config):
        return True
    shell_problem("This command needs a configured AI provider and model. Run /login, then /test-model.")
    return False


def truncate_text(text: str, limit: int = MAX_TOOL_OUTPUT) -> str:
    if len(text) <= limit:
        return text
    return text[:limit].rstrip() + f"\n... truncated {len(text) - limit} chars ..."


def project_relative_path(root: Path, value: str) -> Path | None:
    candidate = Path(value)
    if candidate.is_absolute() or ".." in candidate.parts:
        return None
    resolved = (root / candidate).resolve()
    try:
        resolved.relative_to(root.resolve())
    except ValueError:
        return None
    return resolved


def command_path_arg(value: str | None) -> str | None:
    if not value:
        return None
    return value[1:] if value.startswith("@") else value


def extract_file_mentions(text: str) -> list[str]:
    seen: set[str] = set()
    mentions: list[str] = []
    for match in MENTION_RE.finditer(text):
        mention = match.group(1).rstrip(".,:;)")
        if mention not in seen:
            seen.add(mention)
            mentions.append(mention)
    return mentions


def bash_tool_snapshot(root: Path) -> str:
    command = "printf 'pwd: '; pwd; printf '\\nfiles:\\n'; (rg --files 2>/dev/null || find . -type f | sed 's#^./##') | head -60"
    try:
        result = subprocess.run(["bash", "-lc", command], cwd=root, text=True, capture_output=True, check=False, timeout=5)
    except (OSError, subprocess.TimeoutExpired) as exc:
        return f"bash tool failed: {exc}"
    output = result.stdout or result.stderr or "No bash output."
    return truncate_text(output, 4_000)


def instruction_files(root: Path) -> list[Path]:
    files: list[Path] = []
    for name in INSTRUCTION_FILES:
        path = root / name
        if path.is_file():
            files.append(path)
        elif path.is_dir():
            files.extend(sorted(child for child in path.rglob("*") if child.is_file()))
    return files


def project_read_context(root: Path) -> str:
    instructions = instruction_files(root)
    all_files = iter_project_files(root)
    instruction_set = {path.resolve() for path in instructions}
    project_files = [path for path in all_files if path.resolve() not in instruction_set]
    ordered_files = [*instructions, *project_files] if instructions else project_files
    if not ordered_files:
        return "read phase 1: no readable project text files found."

    sections: list[str] = []
    if instructions:
        sections.append(
            "read phase 1: instruction files found and read first:\n"
            + "\n".join(str(path.relative_to(root)) for path in instructions)
        )
        sections.append("read phase 2: bounded project text-file reads after instructions:")
    else:
        sections.append("read phase 1: no instruction files found; bounded read of project text files:")

    remaining = MAX_PROJECT_READ_CHARS
    emitted = 0
    for path in ordered_files:
        if emitted >= MAX_PROJECT_READ_FILES or remaining <= 0:
            break
        relative = path.relative_to(root)
        text = safe_read(path).strip()
        if not text:
            continue
        budget = min(3_000, remaining)
        excerpt = truncate_text(text, budget)
        sections.append(f"--- {relative} ---\n{excerpt}")
        remaining -= len(excerpt)
        emitted += 1

    omitted = len(ordered_files) - emitted
    if omitted > 0:
        sections.append(f"... omitted {omitted} additional readable project files due to context budget ...")
    return "\n\n".join(sections)


def project_context_key(root: Path) -> str:
    parts: list[str] = []
    for path in [*instruction_files(root), *iter_project_files(root)[:MAX_PROJECT_READ_FILES]]:
        try:
            stat = path.stat()
        except OSError:
            continue
        parts.append(f"{path.relative_to(root)}:{stat.st_mtime_ns}:{stat.st_size}")
    return "|".join(parts)


def cached_project_read_context(root: Path) -> str:
    key = project_context_key(root)
    cache = load_cache(root)
    if cache.project_context_key == key and cache.project_context:
        return "read phase 0: reused cached project file context.\n\n" + cache.project_context
    body = project_read_context(root)
    cache.project_context_key = key
    cache.project_context = body
    save_cache(cache, root)
    return body


def mentioned_file_context(root: Path, prompt: str) -> str:
    sections: list[str] = []
    for mention in extract_file_mentions(prompt):
        path = project_relative_path(root, mention)
        if path is None:
            sections.append(f"@{mention}: rejected; path must stay inside the project.")
            continue
        if not path.exists():
            sections.append(f"@{mention}: not found.")
            continue
        relative = path.relative_to(root)
        if path.is_dir():
            files = [str(child.relative_to(root)) for child in path.rglob("*") if child.is_file()]
            sections.append(f"@{mention} directory listing:\n" + "\n".join(files[:80]))
            continue
        if not path.is_file():
            sections.append(f"@{mention}: not a regular file.")
            continue
        text = safe_read(path)
        sections.append(f"@{relative} file contents:\n{truncate_text(text, 8_000)}")
    return "\n\n".join(sections) if sections else "No @file references were provided."


def ai_tool_context(root: Path, prompt: str, config: TurtlesConfig) -> str:
    return (
        "Turtles CLI local evidence follows. Read evidence is primary. Scanner output, if present in the user task, "
        "is secondary and may be wrong. The model did not execute tools directly.\n\n"
        f"read tool evidence:\n{cached_project_read_context(root)}\n\n"
        f"@file reader:\n{mentioned_file_context(root, prompt)}\n\n"
        f"project signal:\n{project_signal_context(root, config)}\n\n"
        f"bash snapshot:\n{bash_tool_snapshot(root)}"
    )


def finding_file_evidence(root: Path, findings: list[Finding], *, radius: int = 2, max_files: int = 6) -> str:
    if not findings:
        return "No finding-linked file snippets."
    by_path: dict[str, list[int]] = {}
    for finding in findings:
        if finding.path == ".":
            continue
        by_path.setdefault(finding.path, [])
        if finding.line not in by_path[finding.path]:
            by_path[finding.path].append(finding.line)
    sections: list[str] = []
    for relative, line_numbers in list(sorted(by_path.items()))[:max_files]:
        path = project_relative_path(root, relative)
        if path is None or not path.is_file():
            continue
        lines = safe_read(path).splitlines()
        snippets: list[str] = []
        for line_number in sorted(line_numbers)[:4]:
            start = max(1, line_number - radius)
            end = min(len(lines), line_number + radius)
            for current in range(start, end + 1):
                marker = ">" if current == line_number else " "
                snippets.append(f"{marker} {current}: {lines[current - 1]}")
        if snippets:
            sections.append(f"{relative}:\n" + "\n".join(snippets))
    return "\n\n".join(sections) if sections else "No readable finding-linked file snippets."


def finding_file_reads(root: Path, findings: list[Finding], *, max_files: int = 5, max_chars: int = 18_000) -> str:
    paths: list[str] = []
    for finding in findings:
        if finding.path == "." or finding.path in paths:
            continue
        paths.append(finding.path)
    if not paths:
        return "No finding-linked files to read."

    sections: list[str] = []
    remaining = max_chars
    for relative in paths[:max_files]:
        path = project_relative_path(root, relative)
        if path is None or not path.is_file() or remaining <= 0:
            continue
        text = safe_read(path).strip()
        if not text:
            continue
        excerpt = truncate_text(text, min(4_000, remaining))
        sections.append(f"--- {relative} ---\n{excerpt}")
        remaining -= len(excerpt)
    return "\n\n".join(sections) if sections else "No readable finding-linked files."


def print_findings(findings: list[Finding], title: str, mode: TurtleMode) -> None:
    table = Table(title=title, box=box.SIMPLE_HEAVY, header_style=f"bold {mode.color}")
    table.add_column("Severity")
    table.add_column("File")
    table.add_column("Line", justify="right")
    table.add_column("Finding")
    for finding in findings:
        table.add_row(finding.severity, finding.path, str(finding.line), finding.message)
    if not findings:
        table.add_row("ok", ".", "0", "No findings from the local scanner.")
    console.print(table)


def findings_prompt(kind: str, findings: list[Finding]) -> str:
    if not findings:
        return f"Local {kind} scanner returned no findings."
    grouped: dict[str, list[Finding]] = {}
    seen: set[tuple[str, int, str]] = set()
    for finding in findings:
        key = (finding.path, finding.line, finding.message)
        if key in seen:
            continue
        seen.add(key)
        grouped.setdefault(finding.path, []).append(finding)

    lines = [f"Local {kind} scanner findings ({len(seen)} unique findings across {len(grouped)} files):"]
    emitted = 0
    for path, path_findings in sorted(grouped.items()):
        if emitted >= 80:
            break
        lines.append(f"- {path}")
        for finding in path_findings[:5]:
            if emitted >= 80:
                break
            lines.append(f"  - line {finding.line} [{finding.severity}]: {finding.message}")
            emitted += 1
        if len(path_findings) > 5:
            lines.append(f"  - ... {len(path_findings) - 5} more in this file ...")
    if len(seen) > emitted:
        lines.append(f"- ... {len(seen) - emitted} additional unique findings omitted ...")
    return "\n".join(lines)


def scanner_prompt(root: Path, kind: str, findings: list[Finding]) -> str:
    return (
        "Read/instruction-file evidence is primary. Local scanner output is secondary and not ground truth. "
        "Treat low/info findings as triage leads. Only call something confirmed when the file evidence supports it.\n\n"
        f"Project read context:\n{cached_project_read_context(root)}\n\n"
        f"{findings_prompt(kind, findings)}\n\n"
        f"Finding-linked snippets:\n{finding_file_evidence(root, findings)}\n\n"
        f"Finding-linked file reads:\n{finding_file_reads(root, findings)}"
    )


def tool_output_prompt(kind: str, output: str, *, exit_code: int | None = None) -> str:
    lines = [f"Local tool result: {kind}"]
    if exit_code is not None:
        lines.append(f"Exit code: {exit_code}")
    lines.append("Output:")
    lines.append(truncate_text(output.strip() or "No output.", 10_000))
    return "\n".join(lines)


def render_local_result(title: str, output: str, mode: TurtleMode, *, exit_code: int | None = None) -> None:
    body = tool_output_prompt(title, output, exit_code=exit_code)
    border = "green" if exit_code in {None, 0} else "red"
    panel(title, body, mode, border_style=border)


def response_has_fake_tool_call(text: str) -> bool:
    return bool(FAKE_TOOL_RE.search(text))


def response_is_malformed(text: str, contract: str) -> bool:
    lowered = text.lower()
    if response_has_fake_tool_call(text):
        return True
    if contract == "plain_prompt":
        return bool(FENCED_CODE_RE.search(text) or JSON_OBJECT_RE.match(text) or "<tool" in lowered)
    if contract == "prompt_eval":
        return "score" not in lowered or bool(FENCED_CODE_RE.search(text) or JSON_OBJECT_RE.match(text))
    if contract == "markdown_doc":
        return bool(JSON_OBJECT_RE.match(text) or "<tool" in lowered)
    return False


def clean_ai_response(text: str) -> str:
    cleaned = FAKE_TOOL_RE.sub("", text).strip()
    cleaned = re.sub(r"(?im)^\s*(I'll|I will|Let me)\s+(inspect|analyze|read|run|check).*$", "", cleaned)
    return cleaned.strip()


def init_template_body(mode: TurtleMode, *, source: str) -> str:
    return f"""# TURTLE.md

> Source: {source}

## Project Instructions
- Work only inside this repository unless the user explicitly says otherwise.
- Keep secrets, tokens, and local runtime files out of commits.
- Prefer focused edits and project-local tests.
- Treat scanner output as leads; verify against file evidence before reporting defects.
- Use `/code-review`, `/security`, `/docker`, and `/context` before large assistant tasks.

## Active Mode
- {mode.name}: {mode.focus}

## Assistant Files
- Claude: `CLAUDE.md`
- Codex: `AGENTS.md`
- Gemini: `GEMINI.md`
- Turtles CLI: `TURTLE.md`
"""


def run_with_animation(message: str, mode: TurtleMode, action: Callable[[], object]) -> object:
    with processing_animation(message, mode):
        return action()


def project_signal_context(root: Path, config: TurtlesConfig) -> str:
    names = sorted(path.name for path in root.iterdir() if not path.name.startswith(".") or path.name in {".github", ".gitignore"})
    visible = ", ".join(names[:40]) if names else "empty project"
    return (
        f"Project: {root.name}\n"
        f"Top-level files/directories: {visible}\n"
        f"Configured MCP servers: {', '.join(config.mcp_servers) or 'none'}\n"
        f"Configured skills: {', '.join(config.skills) or 'none'}\n"
        f"Configured subagents: {', '.join(config.subagents) or 'none'}"
    )


def choose_assistant_target() -> str:
    selected = choose_from_keyboard("Assistant target", ["claude", "codex", "gemini", "all"], default="claude")
    return selected


def handle_login(args: list[str], root: Path, config: TurtlesConfig) -> TurtlesConfig:
    providers = list(PROVIDERS.values())
    default_provider = PROVIDERS.get(config.provider.provider, PROVIDERS["openrouter"])
    provider_label = choose_from_keyboard("Provider", [provider.label for provider in providers], default=default_provider.label)
    provider = next(provider for provider in providers if provider.label == provider_label)
    username = Prompt.ask("Username", default=config.provider.username or "user")
    base_url = config.provider.base_url if config.provider.provider == provider.key else ""
    if provider.requires_base_url or provider.key in {"custom", "azure-openai"}:
        base_url = Prompt.ask("API base URL", default=base_url or provider.base_url or "https://api.example.com/v1")
    elif provider.base_url and Confirm.ask("Customize API base URL?", default=False):
        base_url = Prompt.ask("API base URL", default=base_url or provider.base_url)

    secret_label = "Ollama host" if provider.key == "ollama" else f"{provider.label} API key"
    if provider.key == "ollama":
        api_key = Prompt.ask(secret_label, default=base_url or provider.base_url)
    else:
        env_secret = os.environ.get(provider.env_var, "")
        if env_secret and Confirm.ask(f"Use {provider.env_var} from environment?", default=True):
            api_key = env_secret
        else:
            api_key = masked_prompt(secret_label)
    model = choose_model(provider.default_models, config.provider.model if config.provider.provider == provider.key else "")
    config.provider = ProviderConfig(provider=provider.key, username=username, api_key=api_key, model=model, base_url=base_url)
    save_config(config, root)
    status(f"Logged in to {provider.label} for this project.", get_mode(config.mode), style="green")
    return config


def choose_model(default_models: tuple[str, ...], current_model: str = "") -> str:
    choices = list(default_models)
    if current_model and current_model not in choices:
        choices.insert(0, current_model)
    choices.append("Custom model...")
    selected = choose_from_keyboard("Default model", choices, default=current_model or choices[0])
    if selected == "Custom model...":
        return Prompt.ask("Model id", default=current_model or default_models[0])
    return selected


def handle_logout(args: list[str], root: Path, config: TurtlesConfig) -> TurtlesConfig:
    config.provider = ProviderConfig()
    save_config(config, root)
    status("Cleared project provider credentials.", get_mode(config.mode), style="green")
    return config


def handle_models(args: list[str], root: Path, config: TurtlesConfig) -> TurtlesConfig:
    if not require_login(config):
        return config
    provider = PROVIDERS.get(config.provider.provider)
    if not provider:
        shell_problem("Active provider is not recognized. Run /provider.")
        return config
    table = Table(title=f"{provider.label} models", box=box.SIMPLE_HEAVY)
    table.add_column("#", justify="right")
    table.add_column("Model")
    table.add_column("Active")
    models = list(provider.default_models)
    if config.provider.model and config.provider.model not in models:
        models.insert(0, config.provider.model)
    for index, model in enumerate(models, start=1):
        table.add_row(str(index), model, "yes" if model == config.provider.model else "")
    console.print(table)
    if Confirm.ask("Switch model?", default=False):
        config.provider.model = choose_model(provider.default_models, config.provider.model)
        save_config(config, root)
        status(f"Active model: {config.provider.model}", get_mode(config.mode), style="green")
    return config


def handle_test_model(args: list[str], root: Path, config: TurtlesConfig) -> TurtlesConfig:
    mode = get_mode(config.mode)
    if not require_login(config):
        return config
    prompt = (
        "Reply with one short sentence confirming model connectivity. "
        "Mention that Turtles CLI supplied local bash/read tool evidence.\n\n"
        f"{ai_tool_context(root, 'connectivity smoke test', config)}"
    )
    try:
        with processing_animation(
            "Testing model connectivity",
            mode,
            phases=["checking active provider", "preparing request", "waiting for model", "reading response"],
        ):
            response = complete_text(
                config,
                "You are a connectivity test endpoint. Keep the response short. You cannot run shell commands directly; rely on the provided local tool evidence.",
                prompt,
                timeout=20.0,
            )
    except LLMError as exc:
        shell_problem(f"Model connectivity failed. {exc}")
        return config
    body = f"provider: {response.provider}\nmodel: {response.model}\nresponse: {response.text or '[empty response]'}"
    panel("Model connectivity ok", body, mode, border_style="green")
    return config


def handle_provider(args: list[str], root: Path, config: TurtlesConfig) -> TurtlesConfig:
    return handle_login(args, root, config)


def handle_customize(args: list[str], root: Path, config: TurtlesConfig) -> TurtlesConfig:
    config.display.prompt_style = Prompt.ask("Prompt style", choices=["claude", "compact", "verbose"], default=config.display.prompt_style)
    config.display.color_theme = Prompt.ask("Color theme", choices=["turtle-green", "classic-dark", "high-contrast"], default=config.display.color_theme)
    config.display.verbosity = Prompt.ask("Verbosity", choices=["quiet", "normal", "verbose"], default=config.display.verbosity)
    config.display.show_animation = Confirm.ask("Show startup animation?", default=config.display.show_animation)
    save_config(config, root)
    return config


def handle_simple_registry(kind: str, args: list[str], root: Path, config: TurtlesConfig) -> TurtlesConfig:
    mode = get_mode(config.mode)
    collection = getattr(config, kind)
    action = choose_from_keyboard(f"{kind} action", ["list", "install", "create"], default="list")
    if action == "list":
        base = root / ".claude" / ("skills" if kind == "skills" else "agents")
        files = []
        if base.exists():
            files = [str(path.relative_to(root)) for path in base.rglob("SKILL.md" if kind == "skills" else "*.md")]
        body = "\n".join(files + collection) if files or collection else "Nothing installed yet."
        panel(kind, body, mode)
    elif action == "install":
        url = Prompt.ask("GitHub or registry URL")
        collection.append(url)
        save_config(config, root)
        status(f"Installed {kind[:-1]} reference: {url}", mode)
    else:
        name = Prompt.ask(f"{kind[:-1].title()} name")
        description = Prompt.ask("Description")
        target = choose_assistant_target()
        if kind == "skills":
            result = create_skill(root, name, description, target=target)
        else:
            result = create_subagent(root, name, description, target=target)
        collection.append(str(result.path.relative_to(root)))
        save_config(config, root)
        created = [str(path.relative_to(root)) for path in result.paths] if result.paths else [str(result.path.relative_to(root))]
        status(f"Created local scaffold template for {result.kind}: " + ", ".join(created), mode)
    return config


def handle_plugins(args: list[str], root: Path, config: TurtlesConfig) -> TurtlesConfig:
    action = choose_from_keyboard("Plugin action", ["list", "install", "create", "enable", "disable"], default="list")
    if action == "list":
        plugin_files = [str(path.relative_to(root)) for path in (root / "plugins").glob("*/.claude-plugin/plugin.json")] if (root / "plugins").exists() else []
        configured = [f"{name}: {'enabled' if enabled else 'disabled'}" for name, enabled in config.plugins.items()]
        body = "\n".join(plugin_files + configured) or "No plugins installed yet."
        panel("plugins", body, get_mode(config.mode))
    elif action == "install":
        url = Prompt.ask("Registry or GitHub URL")
        config.plugins[url] = True
        save_config(config, root)
    elif action == "create":
        name = Prompt.ask("Plugin name")
        description = Prompt.ask("Description")
        target = choose_assistant_target()
        result = create_plugin(root, name, description, author=config.provider.username or "Turtles CLI user", target=target)
        config.plugins[str(result.path.parent.parent.relative_to(root))] = True
        save_config(config, root)
        created = [str(path.relative_to(root)) for path in result.paths] if result.paths else [str(result.path.relative_to(root))]
        status("Created local scaffold template for plugin: " + ", ".join(created), get_mode(config.mode))
    else:
        name = Prompt.ask("Plugin name")
        config.plugins[name] = action == "enable"
        save_config(config, root)
    return config


def handle_hooks(args: list[str], root: Path, config: TurtlesConfig) -> TurtlesConfig:
    action = Prompt.ask("Hook action", choices=["list", "set", "remove"], default="list")
    if action == "list":
        body = "\n".join(f"{name}: {command}" for name, command in config.hooks.items()) or "No hooks configured."
        panel("hooks", body, get_mode(config.mode))
    elif action == "set":
        name = Prompt.ask("Hook", choices=["pre-commit", "pre-push", "post-build"])
        command = Prompt.ask("Command")
        config.hooks[name] = command
        save_config(config, root)
    else:
        name = Prompt.ask("Hook name")
        config.hooks.pop(name, None)
        save_config(config, root)
    return config


def handle_init(args: list[str], root: Path, config: TurtlesConfig) -> TurtlesConfig:
    mode = get_mode(config.mode)
    target = root / "TURTLE.md"
    source = "local Turtles CLI init template; no AI provider/model was used"
    body = init_template_body(mode, source=source)
    if provider_ready(config):
        generated = ai_or_error(
            config,
            mode,
        "Create a TURTLE.md project instruction file for a coding assistant. Return only Markdown for TURTLE.md. Do not claim to have run commands, inspected files beyond the supplied evidence, or verified anything not present in the evidence. Include a short Source line naming the active provider/model.",
            f"Project root: {root.name}\nMode: {mode.name} - {mode.focus}\n{project_signal_context(root, config)}",
            root=root,
            output_contract="markdown_doc",
        )
        if generated:
            source = "active AI provider/model via Turtles CLI"
            body = generated.rstrip() + "\n"

    def write_files() -> None:
        init_project(root)
        target.write_text(body, encoding="utf-8")

    run_with_animation("Initializing project instructions", mode, write_files)
    status(f"Initialized .turtles/config.json and {target.name} using {source}.", mode)
    return load_config(root)


def handle_docs(args: list[str], root: Path, config: TurtlesConfig) -> TurtlesConfig:
    mode = get_mode(config.mode)
    if not require_ai(config):
        return config
    filename = args[0] if args else Prompt.ask("Instruction filename", default="backend.md")
    if Path(filename).is_absolute() or ".." in Path(filename).parts:
        shell_problem("Docs filename must stay inside the project root.")
        return config
    if not filename.endswith(".md"):
        filename = f"{filename}.md"
    goal = " ".join(args[1:]) if len(args) > 1 else ask_project_text(root, "What should this instruction file cover?")
    body = ai_or_error(
        config,
        mode,
        "Create a concise project instruction Markdown file for a coding assistant. Return only Markdown for that instruction file. Do not include implementation code unless the user explicitly requested code examples. Do not claim to have checked or verified anything beyond the supplied evidence.",
        f"Filename: {filename}\nProject root: {root.name}\nRequested content: {goal}",
        root=root,
        output_contract="markdown_doc",
    )
    if not body:
        return config
    target = root / filename
    with processing_animation(f"Writing {filename}", mode):
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(body.rstrip() + "\n", encoding="utf-8")
    status(f"Wrote AI-generated instruction file {target.relative_to(root)}", mode)
    return config


def handle_code_review(args: list[str], root: Path, config: TurtlesConfig) -> TurtlesConfig:
    target = command_path_arg(args[0] if args else None)
    mode = get_mode(config.mode)
    if not require_ai(config):
        return config
    findings = run_with_animation("Running code review", mode, lambda: code_review(root, target))
    summary = scanner_prompt(root, "code review", findings)
    body = ai_or_error(
        config,
        mode,
        "Create one consolidated code-review report from the scanner leads and finding-linked file reads. Read the file evidence before conclusions. Do not convert low-confidence scanner leads into defects. If evidence does not confirm a bug, say it is unconfirmed or omit it. Prioritize real behavioral risks and include concrete verification commands. Do not print raw scanner tables.",
        summary,
        root=root,
    )
    if body:
        markdown_panel("Code review", body, mode)
    return config


def handle_security(args: list[str], root: Path, config: TurtlesConfig) -> TurtlesConfig:
    target = command_path_arg(args[0] if args else None)
    mode = get_mode(config.mode)
    if not require_ai(config):
        return config
    findings = run_with_animation("Running security audit", mode, lambda: security_audit(root, target))
    summary = scanner_prompt(root, "security audit", findings)
    body = ai_or_error(
        config,
        mode,
        "Create one consolidated security report from the scanner leads and finding-linked file reads. Read the file evidence before conclusions. Separate confirmed risks from likely false positives. Do not report a secret unless the evidence looks like a real credential rather than placeholder text, docs, or tests. Include concrete fixes. Do not print raw scanner tables.",
        summary,
        root=root,
    )
    if body:
        markdown_panel("Security audit", body, mode)
    return config


def handle_mcp(args: list[str], root: Path, config: TurtlesConfig) -> TurtlesConfig:
    action = args[0] if args else choose_from_keyboard("MCP action", ["list", "setup-github", "check-github", "add-url", "add-stdio"], default="list")
    if action == "list":
        table = Table(title="MCP Servers", box=box.SIMPLE_HEAVY)
        table.add_column("Name")
        table.add_column("Enabled")
        table.add_column("Transport")
        table.add_column("Target")
        for name, server in config.mcp_servers.items():
            table.add_row(name, str(server.get("enabled", True)), str(server.get("transport", "")), str(server.get("url") or server.get("command") or ""))
        console.print(table)
    elif action == "add-url":
        name = Prompt.ask("Server name")
        url = Prompt.ask("Server URL")
        config.mcp_servers[name] = {"enabled": True, "transport": "http", "url": url, "scope": "project"}
        save_config(config, root)
    elif action == "add-stdio":
        name = Prompt.ask("Server name")
        command = Prompt.ask("stdio command")
        config.mcp_servers[name] = {"enabled": True, "transport": "stdio", "command": command, "scope": "project"}
        save_config(config, root)
    elif action in {"setup-github", "github-setup"}:
        mode = get_mode(config.mode)
        body = run_with_animation("Setting up GitHub MCP", mode, lambda: setup_github_mcp(root, config))
        render_local_result("GitHub MCP setup", body, mode)
    elif action in {"check", "check-github", "github"}:
        mode = get_mode(config.mode)
        body = run_with_animation("Checking GitHub MCP", mode, lambda: github_mcp_diagnostics(config, root))
        render_local_result("GitHub MCP diagnostics", body, mode)
    return config


def github_mcp_wrapper(root: Path) -> Path:
    return config_dir(root) / "github-mcp-server"


def setup_github_mcp(root: Path, config: TurtlesConfig) -> str:
    native = shutil.which("github-mcp-server")
    docker = shutil.which("docker")
    lines: list[str] = []
    if native:
        command = "github-mcp-server"
        lines.append(f"using native github-mcp-server: {native}")
    elif docker:
        wrapper = github_mcp_wrapper(root)
        wrapper.parent.mkdir(parents=True, exist_ok=True)
        wrapper.write_text(
            """#!/usr/bin/env sh
set -eu

if [ -z "${GITHUB_PERSONAL_ACCESS_TOKEN:-}" ] && [ -n "${GITHUB_TOKEN:-}" ]; then
  export GITHUB_PERSONAL_ACCESS_TOKEN="$GITHUB_TOKEN"
fi

if [ -z "${GITHUB_PERSONAL_ACCESS_TOKEN:-}" ]; then
  echo "Set GITHUB_TOKEN or GITHUB_PERSONAL_ACCESS_TOKEN before starting Turtles CLI." >&2
  exit 1
fi

exec docker run -i --rm \\
  -e GITHUB_PERSONAL_ACCESS_TOKEN \\
  ghcr.io/github/github-mcp-server "$@"
""",
            encoding="utf-8",
        )
        os.chmod(wrapper, 0o700)
        command = str(wrapper.relative_to(root))
        lines.append(f"created docker wrapper: {command}")
    else:
        return "failed: install docker or github-mcp-server, then run /mcp setup-github again."

    config.mcp_servers["github"] = {"enabled": True, "transport": "stdio", "command": command, "scope": "project"}
    save_config(config, root)
    lines.append("configured project MCP server: github")
    lines.append(f"GITHUB_TOKEN set: {'yes' if os.environ.get('GITHUB_TOKEN') else 'no'}")
    lines.append(f"GITHUB_PERSONAL_ACCESS_TOKEN set: {'yes' if os.environ.get('GITHUB_PERSONAL_ACCESS_TOKEN') else 'no'}")
    if not os.environ.get("GITHUB_TOKEN") and not os.environ.get("GITHUB_PERSONAL_ACCESS_TOKEN"):
        lines.append("next: export GITHUB_TOKEN=... in the terminal before starting turtles.")
    lines.append("")
    lines.append(github_mcp_diagnostics(config, root))
    return "\n".join(lines)


def github_mcp_diagnostics(config: TurtlesConfig, root: Path | None = None) -> str:
    server = config.mcp_servers.get("github", {})
    command = str(server.get("command") or "github-mcp-server")
    command_parts = shlex.split(command) if command else ["github-mcp-server"]
    executable = command_parts[0]
    candidate = (root / executable).resolve() if root and not Path(executable).is_absolute() else Path(executable)
    found = str(candidate) if ("/" in executable or "\\" in executable) and candidate.exists() else shutil.which(executable)
    lines = [
        f"configured: {'yes' if server else 'no'}",
        f"enabled: {server.get('enabled', False)}",
        f"transport: {server.get('transport', '')}",
        f"command: {command}",
        f"found on PATH: {'yes - ' + found if found else 'no'}",
        f"GITHUB_TOKEN set: {'yes' if os.environ.get('GITHUB_TOKEN') else 'no'}",
        f"GITHUB_PERSONAL_ACCESS_TOKEN set: {'yes' if os.environ.get('GITHUB_PERSONAL_ACCESS_TOKEN') else 'no'}",
    ]
    if found:
        try:
            result = subprocess.run(command_parts + ["--help"], cwd=root, text=True, capture_output=True, check=False, timeout=5)
            output = (result.stdout or result.stderr).strip().splitlines()
            lines.append(f"help check exit: {result.returncode}")
            if output:
                lines.append(f"help check first line: {output[0]}")
        except (OSError, subprocess.TimeoutExpired) as exc:
            lines.append(f"help check failed: {exc}")
    else:
        lines.append("fix: install GitHub's github-mcp-server and make it visible on PATH, or update /mcp add-stdio.")
    return "\n".join(lines)


def handle_mcp_suggestion(args: list[str], root: Path, config: TurtlesConfig) -> TurtlesConfig:
    mode = get_mode(config.mode)
    body = ai_or_error(
        config,
        mode,
        "Recommend concrete MCP servers for this repository based only on supplied project evidence. Do not claim a server is installed, working, or verified unless the evidence says so. Avoid placeholders. Explain why each server is useful and give exact verification steps.",
        project_signal_context(root, config),
        root=root,
    )
    if body:
        markdown_panel("MCP suggestions", body, mode)
    return config


def handle_docker(args: list[str], root: Path, config: TurtlesConfig) -> TurtlesConfig:
    mode = get_mode(config.mode)
    if not require_ai(config):
        return config
    findings = run_with_animation("Running Docker audit", mode, lambda: docker_audit(root))
    summary = scanner_prompt(root, "docker audit", findings)
    body = ai_or_error(
        config,
        mode,
        "Create one consolidated Docker report from the local scanner evidence. De-duplicate repeated files/lines, separate confirmed risks from likely false positives, and include quick verification steps. Do not print raw scanner tables.",
        summary,
        root=root,
    )
    if body:
        markdown_panel("Docker audit", body, mode)
    return config


def handle_api(args: list[str], root: Path, config: TurtlesConfig) -> TurtlesConfig:
    mode = get_mode(config.mode)
    body = ai_or_error(
        config,
        mode,
        "Suggest concrete APIs that could be useful for this repository based only on supplied project evidence. Do not claim an API is already integrated or verified unless the evidence says so. Avoid generic placeholders.",
        project_signal_context(root, config),
        root=root,
    )
    if body:
        markdown_panel("API suggestions", body, mode)
    return config


def handle_ai(args: list[str], root: Path, config: TurtlesConfig) -> TurtlesConfig:
    mode = get_mode(config.mode)
    body = ai_or_error(
        config,
        mode,
        "Recommend AI provider/model options for this repository's workflow based only on supplied project evidence. Be concrete, avoid mock provider behavior, and do not claim compatibility was tested unless the evidence says so.",
        project_signal_context(root, config),
        root=root,
    )
    if body:
        markdown_panel("AI options", body, mode)
    return config


def handle_github(args: list[str], root: Path, config: TurtlesConfig) -> TurtlesConfig:
    mode = get_mode(config.mode)
    choices = ["status", "branch", "commit", "push", "pr-create", "pr-list", "issue-list", "repo-view", "mcp-setup", "mcp-check"]
    subcommand = args[0] if args else choose_from_keyboard("GitHub action", choices, default="status")
    commands: dict[str, list[str]] = {
        "status": ["git", "status", "--short"],
        "branch": ["git", "branch", "--show-current"],
        "push": ["git", "push"],
        "pr-list": ["gh", "pr", "list"],
        "issue-list": ["gh", "issue", "list"],
        "repo-view": ["gh", "repo", "view"],
    }
    if subcommand == "mcp-check":
        body = run_with_animation("Checking GitHub MCP", mode, lambda: github_mcp_diagnostics(config, root))
        render_local_result("GitHub MCP diagnostics", body, mode)
        return config
    if subcommand == "mcp-setup":
        body = run_with_animation("Setting up GitHub MCP", mode, lambda: setup_github_mcp(root, config))
        render_local_result("GitHub MCP setup", body, mode)
        return config
    if subcommand == "commit":
        message = " ".join(args[1:]) or Prompt.ask("Commit message")
        command = ["git", "add", "."]
        with processing_animation("Creating git commit", mode):
            subprocess.run(command, cwd=root, check=False)
            result = subprocess.run(["git", "commit", "-m", message], cwd=root, text=True, capture_output=True, check=False)
    elif subcommand in {"pr", "pr-create"}:
        with processing_animation("Creating GitHub PR", mode):
            result = subprocess.run(["gh", "pr", "create", "--web"], cwd=root, text=True, capture_output=True, check=False)
    else:
        with processing_animation(f"Running github {subcommand}", mode):
            result = subprocess.run(commands.get(subcommand, ["git", subcommand]), cwd=root, text=True, capture_output=True, check=False)
    output = result.stdout or result.stderr or "No output."
    render_local_result(f"github {subcommand}", output, mode, exit_code=result.returncode)
    return config


def handle_suggest(kind: str, args: list[str], root: Path, config: TurtlesConfig) -> TurtlesConfig:
    mode = get_mode(config.mode)
    body = ai_or_error(
        config,
        mode,
        f"Suggest concrete {kind} to create for this repository based only on supplied project evidence. Avoid mock names. Include the exact purpose for each. Do not claim the {kind} already exist or were verified unless the evidence says so.",
        project_signal_context(root, config),
        root=root,
    )
    if body:
        markdown_panel(f"Suggested {kind}", body, mode)
    return config


def handle_create_prompt(args: list[str], root: Path, config: TurtlesConfig) -> TurtlesConfig:
    mode = get_mode(config.mode)
    if not require_ai(config):
        return config
    goal = ask_project_text(root, "Goal")
    context = ask_project_text(root, "Context")
    output = ask_project_text(root, "Desired output")
    prompt = f"Goal: {goal}\n\nContext: {context}\n\nOutput: {output}"
    body = ai_or_error(
        config,
        mode,
        "Create a strong coding-assistant prompt from these fields. Return a prompt only, written as plain Markdown text. Do not write implementation code, fenced code blocks, JSON, YAML, or tool calls unless the user's requested output explicitly asks for code. Include scope, constraints, verification, and expected output format.",
        prompt,
        root=root,
        output_contract="plain_prompt",
    )
    if body:
        markdown_panel("Created prompt", body, mode)
    return config


def handle_enhance_prompt(args: list[str], root: Path, config: TurtlesConfig) -> TurtlesConfig:
    prompt = " ".join(args) or ask_project_text(root, "Prompt")
    mode = get_mode(config.mode)
    body = ai_or_error(
        config,
        mode,
        "Enhance this prompt for a coding assistant. Return only the improved prompt with concise sections.",
        prompt,
        root=root,
        output_contract="plain_prompt",
    )
    if body:
        markdown_panel("Enhanced prompt", body, mode)
    return config


def handle_prompt_eval(args: list[str], root: Path, config: TurtlesConfig) -> TurtlesConfig:
    prompt = " ".join(args) or ask_project_text(root, "Prompt")
    mode = get_mode(config.mode)
    body = ai_or_error(
        config,
        mode,
        "Evaluate the prompt for a coding assistant. Score clarity, specificity, safety, and output quality from 0-100. Include concise fixes.",
        prompt,
        root=root,
        output_contract="prompt_eval",
    )
    if body:
        markdown_panel("Prompt evaluation", body, mode)
    return config


def handle_simulation(args: list[str], root: Path, config: TurtlesConfig) -> TurtlesConfig:
    console.print(
        "[yellow]Important: a simulation scenario is a prompt with optional skills, sub-agents, plugins, "
        "and @path project file references. It does not execute or modify files; it passes local evidence "
        "to the AI for a risk/plan/test assessment.[/yellow]"
    )
    prompt = " ".join(args) or ask_project_text(root, "Scenario prompt")
    code_involved = Confirm.ask("Does this scenario involve code?", default=True)
    mode = get_mode(config.mode)
    body = ai_or_error(
        config,
        mode,
        "Simulate how a coding assistant would handle this scenario. Use the provided bash/read tool evidence, including @file contents. Return a concise risk/plan/test assessment with a final readiness grade.",
        f"Code involved: {code_involved}\n\nScenario:\n{prompt}",
        root=root,
    )
    if body:
        markdown_panel("Simulation grade", body, mode)
    return config


def handle_turtle_mode(args: list[str], root: Path, config: TurtlesConfig) -> TurtlesConfig:
    from .turtle_mode import run_turtle_mode

    return run_turtle_mode(args, root, config)


def handle_help(args: list[str], root: Path, config: TurtlesConfig) -> TurtlesConfig:
    table = Table(title="Turtles CLI Commands", box=box.SIMPLE_HEAVY, header_style="bold green")
    table.add_column("Command")
    table.add_column("Purpose")
    commands = {
        "/login": "Configure project-scoped provider credentials.",
        "/logout": "Clear project-scoped provider credentials.",
        "/models": "List and switch models for the active provider.",
        "/test-model": "Send a live request to verify the active provider/model.",
        "/provider": "Switch provider or re-authenticate.",
        "/customize-cli": "Change prompt style, theme, verbosity, and animation.",
        "/skills": "Install or create skills.",
        "/subagents": "Install or create sub-agents.",
        "/hooks": "Manage lifecycle hooks.",
        "/plugins": "Install, create, enable, or disable plugins.",
        "/init": "Create .turtles/config.json and TURTLE.md.",
        "/docs": "Create a custom instruction Markdown file with the active model.",
        "/doc": "Alias for /docs.",
        "/code-review": "Run local code review heuristics.",
        "/security": "Scan for secrets and risky patterns.",
        "/mcp": "List, add, or check MCP servers. GitHub MCP is enabled by default.",
        "/mcp-suggestion": "Suggest relevant MCP servers.",
        "/docker": "Audit Dockerfile and Compose files.",
        "/api": "Suggest relevant APIs.",
        "/AI": "Suggest open/free AI providers and models.",
        "/github": "Choose GitHub-oriented git/gh/MCP actions.",
        "/suggest-skills": "Suggest skills for this project.",
        "/suggest-plugins": "Suggest plugins for this project.",
        "/suggest-subagents": "Suggest sub-agents for this project.",
        "/create-prompt": "Guided prompt creation.",
        "/enhance-prompt": "Improve a prompt.",
        "/prompt-eval": "Score prompt quality.",
        "/simulation": "Grade a prompt scenario before running it.",
        "/turtle-mode": "Multi-agent orchestration: run 2 code assistants on the same project across machines.",
        "/ai-detect": "Estimate AI-generated content markers.",
        "/context": "Estimate context window usage.",
        "/bash": "Run a shell command from the project root.",
        "/web-search": "Search the web for project research.",
        "/mode": "Switch turtle mode with keyboard autocomplete.",
        "/exit": "Leave the shell.",
    }
    for name, purpose in commands.items():
        table.add_row(name, purpose)
    console.print(table)
    return config


def handle_ai_detect(args: list[str], root: Path, config: TurtlesConfig) -> TurtlesConfig:
    mode = get_mode(config.mode)
    if not require_ai(config):
        return config
    _estimate, findings = run_with_animation("Collecting AI-origin marker leads", mode, lambda: ai_detect(root))
    body = ai_or_error(
        config,
        mode,
        "Create one AI-origin marker review from read evidence and high-confidence marker leads. This is not a detector and must not output a percent-likelihood. Read instruction files and project files before conclusions. Use 'unknown' unless there is explicit provenance text such as generated-by markers. Docs mentioning AI tools, project instructions, placeholders, normal style, or long prose are not proof. List only files worth inspecting and explain why. Do not print raw scanner tables.",
        scanner_prompt(root, "AI-origin marker leads", findings),
        root=root,
    )
    if body:
        markdown_panel("AI-origin marker review", body, mode)
    return config


def handle_context(args: list[str], root: Path, config: TurtlesConfig) -> TurtlesConfig:
    mode = get_mode(config.mode)
    cache = run_with_animation("Estimating context usage", mode, lambda: load_cache(root))
    segments = args if args else cache.context_segments
    provider = PROVIDERS.get(config.provider.provider)
    window = provider.context_window if provider else 128_000
    usage = context_usage(segments, window=window, model=config.provider.model or "not logged in")
    render_context_usage(usage, mode)
    if cache.recent_commands:
        panel("Recent commands", "\n".join(cache.recent_commands[-8:]), mode)
    return config


def handle_mode(args: list[str], root: Path, config: TurtlesConfig) -> TurtlesConfig:
    mode = choose_mode(config.mode)
    config.mode = mode.key
    save_config(config, root)
    status(f"{mode.name} mode active: {mode.focus}", mode)
    return config


def handle_bash(args: list[str], root: Path, config: TurtlesConfig) -> TurtlesConfig:
    mode = get_mode(config.mode)
    command = " ".join(args) or Prompt.ask("bash")
    with processing_animation("Running shell command", mode):
        bash_probe = subprocess.run(["bash", "-lc", "printf ok"], cwd=root, text=True, capture_output=True, check=False)
        if bash_probe.returncode == 0:
            result = subprocess.run(["bash", "-lc", command], cwd=root, text=True, capture_output=True, check=False)
        else:
            result = subprocess.run(command, cwd=root, text=True, capture_output=True, shell=True, check=False)
    output = result.stdout or result.stderr or "No output."
    render_local_result(f"bash exit {result.returncode}", output, mode, exit_code=result.returncode)
    return config


def handle_web_search(args: list[str], root: Path, config: TurtlesConfig) -> TurtlesConfig:
    mode = get_mode(config.mode)
    query = " ".join(args) or Prompt.ask("Search query")
    url = f"https://duckduckgo.com/html/?q={urllib.parse.quote_plus(query)}"
    with processing_animation("Searching web", mode):
        with httpx.Client(timeout=10.0, follow_redirects=True, headers={"User-Agent": "turtles-cli/0.1"}) as client:
            response = client.get(url)
            response.raise_for_status()
    matches = re.findall(r'class="result__a"[^>]*href="([^"]+)"[^>]*>(.*?)</a>', response.text, flags=re.S)
    lines: list[str] = []
    for raw_url, raw_title in matches[:5]:
        title = re.sub(r"<.*?>", "", raw_title)
        parsed = urllib.parse.urlparse(html.unescape(raw_url))
        params = urllib.parse.parse_qs(parsed.query)
        destination = params.get("uddg", [html.unescape(raw_url)])[0]
        lines.append(f"{html.unescape(title)}\n{destination}")
    evidence = "\n\n".join(lines) if lines else "No results found."
    render_local_result("Web search", f"Query: {query}\n\n{evidence}", mode)
    return config


def ai_or_error(
    config: TurtlesConfig,
    mode: TurtleMode,
    system: str,
    prompt: str,
    *,
    root: Path | None = None,
    output_contract: str = "",
) -> str:
    if not provider_ready(config):
        shell_problem("No AI provider/model is configured. Run /login, then /test-model.")
        return ""
    enriched_prompt = prompt
    enriched_system = system
    if root is not None:
        enriched_system = (
            system
            + "\n\nYou are inside Turtles CLI, but you do not have live tools. "
            "The CLI already ran the local tools and supplied their evidence below. "
            "Use the read tool evidence before asking about project files; instruction files are intentionally placed before project file reads. "
            "Return the final user-facing answer only. Never emit XML/tool markup, '<tool_call>', 'bash execute:', "
            "or text saying you will inspect/read/run/check files. If evidence is insufficient, state the missing evidence "
            "as a short request for a specific /bash command or @file reference instead of pretending to run it."
        )
        enriched_prompt = f"{ai_tool_context(root, prompt, config)}\n\nUser task:\n{prompt}"
    try:
        with processing_animation(
            "AI processing",
            mode,
            phases=["checking active provider", "preparing request", "waiting for model", "reading response"],
        ):
            response = complete_text(config, enriched_system, enriched_prompt)
            if response_has_fake_tool_call(response.text) or (output_contract and response_is_malformed(response.text, output_contract)):
                repair_prompt = (
                    "Your previous answer violated the output contract. Rewrite it as a final answer only.\n"
                    f"Output contract: {output_contract or 'final answer'}.\n"
                    "Rules: no <tool_call>, no bash execute text, no promises to inspect files, no invented command output. "
                    "For plain_prompt, return Markdown prose for a prompt, not implementation code, JSON, YAML, or fenced code. "
                    "For prompt_eval, include a visible score and concise fixes, with no fenced code. "
                    "Use only the evidence already provided. If more evidence is needed, request the exact /bash command or @file reference.\n\n"
                    f"Previous answer:\n{response.text}\n\nOriginal task and evidence:\n{enriched_prompt}"
                )
                response = complete_text(config, enriched_system, repair_prompt)
        status(f"Used {response.provider} / {response.model}.", mode, style="green")
        return clean_ai_response(response.text)
    except LLMError as exc:
        shell_problem(f"AI provider failed. {exc}")
        return ""


def handle_user_prompt(args: list[str], root: Path, config: TurtlesConfig) -> TurtlesConfig:
    prompt = " ".join(args)
    mode = get_mode(config.mode)
    body = ai_or_error(
        config,
        mode,
        f"You are Turtles CLI in {mode.name} mode. Help like a pragmatic coding assistant. Keep answers concise and actionable.",
        prompt,
        root=root,
    )
    if body:
        markdown_panel("Assistant", body, mode)
    return config


HANDLERS: dict[str, CommandHandler] = {
    "/login": handle_login,
    "/logout": handle_logout,
    "/models": handle_models,
    "/test-model": handle_test_model,
    "/test-ai": handle_test_model,
    "/provider": handle_provider,
    "/customize-cli": handle_customize,
    "/skills": lambda args, root, config: handle_simple_registry("skills", args, root, config),
    "/subagents": lambda args, root, config: handle_simple_registry("subagents", args, root, config),
    "/hooks": handle_hooks,
    "/plugins": handle_plugins,
    "/init": handle_init,
    "/docs": handle_docs,
    "/doc": handle_docs,
    "/code-review": handle_code_review,
    "/security": handle_security,
    "/mcp": handle_mcp,
    "/mcp-suggestion": handle_mcp_suggestion,
    "/docker": handle_docker,
    "/api": handle_api,
    "/AI": handle_ai,
    "/github": handle_github,
    "/suggest-skills": lambda args, root, config: handle_suggest("skills", args, root, config),
    "/suggest-plugins": lambda args, root, config: handle_suggest("plugins", args, root, config),
    "/suggest-subagents": lambda args, root, config: handle_suggest("subagents", args, root, config),
    "/create-prompt": handle_create_prompt,
    "/enhance-prompt": handle_enhance_prompt,
    "/prompt-eval": handle_prompt_eval,
    "/simulation": handle_simulation,
    "/turtle-mode": handle_turtle_mode,
    "/help": handle_help,
    "/ai-detect": handle_ai_detect,
    "/context": handle_context,
    "/mode": handle_mode,
    "/bash": handle_bash,
    "/web-search": handle_web_search,
    "/search": handle_web_search,
}


def dispatch(line: str, root: Path, config: TurtlesConfig) -> tuple[bool, TurtlesConfig]:
    stripped = line.strip()
    if not stripped:
        return True, config
    if stripped in {"/exit", "/quit"}:
        return False, config
    if not stripped.startswith("/"):
        return True, handle_user_prompt([stripped], root, config)
    command, *args = stripped.split()
    handler = HANDLERS.get(command)
    if handler is None:
        shell_problem(f"Unknown command: {command}. Run /help.")
        return True, config
    try:
        command_pick_animation(command, get_mode(config.mode), enabled=config.display.show_animation)
        return True, handler(args, root, config)
    except Exception as exc:  # noqa: BLE001 - interactive CLI should recover gracefully.
        shell_problem(str(exc))
        return True, config
