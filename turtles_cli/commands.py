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

from .audits import Finding, ai_detect, code_review, context_usage, docker_audit, security_audit
from .config import ProviderConfig, TurtlesConfig, init_project, is_logged_in, load_config, save_config
from .llm import LLMError, complete_text, provider_ready
from .modes import TurtleMode, get_mode
from .prompting import choose_from_keyboard
from .providers import PROVIDERS
from .scaffold import create_plugin, create_skill, create_subagent
from .session import load_cache
from .ui import console, markdown_panel, masked_prompt, panel, processing_animation, render_context_usage, shell_problem, status


CommandHandler = Callable[[list[str], Path, TurtlesConfig], TurtlesConfig]


def require_login(config: TurtlesConfig) -> bool:
    if is_logged_in(config):
        return True
    console.print("[yellow]Run /login first. Provider-backed commands unlock after project-scoped credentials are configured.[/yellow]")
    return False


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
    prompt = "Reply with one short sentence confirming model connectivity."
    try:
        with processing_animation(
            "Testing model connectivity",
            mode,
            phases=["checking active provider", "preparing request", "waiting for model", "reading response"],
        ):
            response = complete_text(
                config,
                "You are a connectivity test endpoint. Keep the response short.",
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
        status(f"Created {result.kind}: " + ", ".join(created), mode)
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
        status("Created plugin: " + ", ".join(created), get_mode(config.mode))
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
    body = f"""# TURTLE.md

## Project Instructions
- Work only inside this repository unless the user explicitly says otherwise.
- Keep secrets, tokens, and local runtime files out of commits.
- Prefer focused edits and project-local tests.
- Use `/code-review`, `/security`, `/docker`, and `/context` before large assistant tasks.

## Active Mode
- {mode.name}: {mode.focus}

## Assistant Files
- Claude: `CLAUDE.md`
- Codex: `AGENTS.md`
- Gemini: `GEMINI.md`
- Turtles CLI: `TURTLE.md`
"""
    def write_files() -> None:
        init_project(root)
        target.write_text(body, encoding="utf-8")

    run_with_animation("Initializing project instructions", mode, write_files)
    status(f"Initialized .turtles/config.json and {target.name}", mode)
    return load_config(root)


def handle_docs(args: list[str], root: Path, config: TurtlesConfig) -> TurtlesConfig:
    mode = get_mode(config.mode)
    filename = args[0] if args else Prompt.ask("Instruction filename", default="backend.md")
    if Path(filename).is_absolute() or ".." in Path(filename).parts:
        shell_problem("Docs filename must stay inside the project root.")
        return config
    if not filename.endswith(".md"):
        filename = f"{filename}.md"
    goal = " ".join(args[1:]) if len(args) > 1 else Prompt.ask("What should this instruction file cover?")
    body = ai_or_error(
        config,
        mode,
        "Create a concise project instruction Markdown file for a coding assistant. Return only Markdown.",
        f"Filename: {filename}\nProject root: {root.name}\nRequested content: {goal}",
    )
    if not body:
        return config
    target = root / filename
    with processing_animation(f"Writing {filename}", mode):
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(body.rstrip() + "\n", encoding="utf-8")
    status(f"Wrote {target.relative_to(root)}", mode)
    return config


def handle_code_review(args: list[str], root: Path, config: TurtlesConfig) -> TurtlesConfig:
    target = args[0] if args else None
    mode = get_mode(config.mode)
    findings = run_with_animation("Running code review", mode, lambda: code_review(root, target))
    print_findings(findings, "Code Review", mode)
    return config


def handle_security(args: list[str], root: Path, config: TurtlesConfig) -> TurtlesConfig:
    target = args[0] if args else None
    mode = get_mode(config.mode)
    findings = run_with_animation("Running security audit", mode, lambda: security_audit(root, target))
    print_findings(findings, "Security Audit", mode)
    return config


def handle_mcp(args: list[str], root: Path, config: TurtlesConfig) -> TurtlesConfig:
    action = args[0] if args else choose_from_keyboard("MCP action", ["list", "check-github", "add-url", "add-stdio"], default="list")
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
    elif action in {"check", "check-github", "github"}:
        mode = get_mode(config.mode)
        body = run_with_animation("Checking GitHub MCP", mode, lambda: github_mcp_diagnostics(config))
        panel("GitHub MCP", body, mode)
    return config


def github_mcp_diagnostics(config: TurtlesConfig) -> str:
    server = config.mcp_servers.get("github", {})
    command = str(server.get("command") or "github-mcp-server")
    executable = shlex.split(command)[0] if command else "github-mcp-server"
    found = shutil.which(executable)
    lines = [
        f"configured: {'yes' if server else 'no'}",
        f"enabled: {server.get('enabled', False)}",
        f"transport: {server.get('transport', '')}",
        f"command: {command}",
        f"found on PATH: {'yes - ' + found if found else 'no'}",
        f"GITHUB_TOKEN set: {'yes' if os.environ.get('GITHUB_TOKEN') else 'no'}",
    ]
    if found:
        try:
            result = subprocess.run(shlex.split(command) + ["--help"], text=True, capture_output=True, check=False, timeout=5)
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
        "Recommend concrete MCP servers for this repository. Avoid placeholders. Explain why each server is useful and how to verify it.",
        project_signal_context(root, config),
    )
    if body:
        markdown_panel("MCP suggestions", body, mode)
    return config


def handle_docker(args: list[str], root: Path, config: TurtlesConfig) -> TurtlesConfig:
    mode = get_mode(config.mode)
    findings = run_with_animation("Running Docker audit", mode, lambda: docker_audit(root))
    print_findings(findings, "Docker Audit", mode)
    return config


def handle_api(args: list[str], root: Path, config: TurtlesConfig) -> TurtlesConfig:
    mode = get_mode(config.mode)
    body = ai_or_error(
        config,
        mode,
        "Suggest concrete APIs that would be useful for this repository. Avoid generic placeholders.",
        project_signal_context(root, config),
    )
    if body:
        markdown_panel("API suggestions", body, mode)
    return config


def handle_ai(args: list[str], root: Path, config: TurtlesConfig) -> TurtlesConfig:
    mode = get_mode(config.mode)
    body = ai_or_error(
        config,
        mode,
        "Recommend AI provider/model options for this repository's workflow. Be concrete and avoid mock provider behavior.",
        project_signal_context(root, config),
    )
    if body:
        markdown_panel("AI options", body, mode)
    return config


def handle_github(args: list[str], root: Path, config: TurtlesConfig) -> TurtlesConfig:
    choices = ["status", "branch", "commit", "push", "pr-create", "pr-list", "issue-list", "repo-view", "mcp-check"]
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
        mode = get_mode(config.mode)
        body = run_with_animation("Checking GitHub MCP", mode, lambda: github_mcp_diagnostics(config))
        panel("GitHub MCP", body, mode)
        return config
    if subcommand == "commit":
        message = " ".join(args[1:]) or Prompt.ask("Commit message")
        command = ["git", "add", "."]
        with processing_animation("Creating git commit", get_mode(config.mode)):
            subprocess.run(command, cwd=root, check=False)
            result = subprocess.run(["git", "commit", "-m", message], cwd=root, text=True, capture_output=True, check=False)
    elif subcommand in {"pr", "pr-create"}:
        with processing_animation("Creating GitHub PR", get_mode(config.mode)):
            result = subprocess.run(["gh", "pr", "create", "--web"], cwd=root, text=True, capture_output=True, check=False)
    else:
        with processing_animation(f"Running github {subcommand}", get_mode(config.mode)):
            result = subprocess.run(commands.get(subcommand, ["git", subcommand]), cwd=root, text=True, capture_output=True, check=False)
    output = result.stdout or result.stderr or "No output."
    panel(f"github {subcommand}", output.strip(), get_mode(config.mode))
    return config


def handle_suggest(kind: str, args: list[str], root: Path, config: TurtlesConfig) -> TurtlesConfig:
    mode = get_mode(config.mode)
    body = ai_or_error(
        config,
        mode,
        f"Suggest concrete {kind} to create for this repository. Avoid mock names. Include the exact purpose for each.",
        project_signal_context(root, config),
    )
    if body:
        markdown_panel(f"Suggested {kind}", body, mode)
    return config


def handle_create_prompt(args: list[str], root: Path, config: TurtlesConfig) -> TurtlesConfig:
    goal = Prompt.ask("Goal")
    context = Prompt.ask("Context")
    output = Prompt.ask("Desired output")
    prompt = f"Goal: {goal}\n\nContext: {context}\n\nOutput: {output}\n\nConstraints:\n- Stay within the project folder.\n- State assumptions.\n- Include verification steps."
    panel("Created prompt", prompt, get_mode(config.mode))
    return config


def handle_enhance_prompt(args: list[str], root: Path, config: TurtlesConfig) -> TurtlesConfig:
    prompt = " ".join(args) or Prompt.ask("Prompt")
    mode = get_mode(config.mode)
    body = ai_or_error(
        config,
        mode,
        "Enhance this prompt for a coding assistant. Return only the improved prompt with concise sections.",
        prompt,
    )
    if body:
        markdown_panel("Enhanced prompt", body, mode)
    return config


def handle_prompt_eval(args: list[str], root: Path, config: TurtlesConfig) -> TurtlesConfig:
    prompt = " ".join(args) or Prompt.ask("Prompt")
    mode = get_mode(config.mode)
    body = ai_or_error(
        config,
        mode,
        "Evaluate the prompt for a coding assistant. Score clarity, specificity, safety, and output quality from 0-100. Include concise fixes.",
        prompt,
    )
    if body:
        markdown_panel("Prompt evaluation", body, mode)
    return config


def handle_simulation(args: list[str], root: Path, config: TurtlesConfig) -> TurtlesConfig:
    console.print("[yellow]Important: a simulation scenario is just a prompt with optional skills, sub-agents, or plugins. It does not execute the work.[/yellow]")
    prompt = " ".join(args) or Prompt.ask("Scenario prompt")
    code_involved = Confirm.ask("Does this scenario involve code?", default=True)
    mode = get_mode(config.mode)
    body = ai_or_error(
        config,
        mode,
        "Simulate how a coding assistant would handle this scenario. Return a concise risk/plan/test assessment with a final readiness grade.",
        f"Code involved: {code_involved}\n\nScenario:\n{prompt}",
    )
    if body:
        markdown_panel("Simulation grade", body, mode)
    return config


def handle_turtle_mode(args: list[str], root: Path, config: TurtlesConfig) -> TurtlesConfig:
    shell_problem("Turtle Mode orchestration is not implemented yet. No mock run was started.")
    return config


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
        "/turtle-mode": "Future multi-agent orchestration stub.",
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
    estimate, findings = run_with_animation("Running AI marker scan", mode, lambda: ai_detect(root))
    print_findings(findings, f"AI Detection Estimate: {estimate}%", mode)
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
    from .modes import MODES

    labels = [mode.name for mode in MODES.values()]
    current = get_mode(config.mode)
    selected = choose_from_keyboard("Mode", labels, default=current.name)
    for mode in MODES.values():
        if mode.name == selected:
            config.mode = mode.key
            save_config(config, root)
            status(f"{mode.name} mode active: {mode.focus}", mode)
            console.print()
            from .ui import build_mascot

            console.print(build_mascot(mode))
            return config
    return config


def handle_bash(args: list[str], root: Path, config: TurtlesConfig) -> TurtlesConfig:
    command = " ".join(args) or Prompt.ask("bash")
    with processing_animation("Running shell command", get_mode(config.mode)):
        bash_probe = subprocess.run(["bash", "-lc", "printf ok"], cwd=root, text=True, capture_output=True, check=False)
        if bash_probe.returncode == 0:
            result = subprocess.run(["bash", "-lc", command], cwd=root, text=True, capture_output=True, check=False)
        else:
            result = subprocess.run(command, cwd=root, text=True, capture_output=True, shell=True, check=False)
    output = result.stdout or result.stderr or "No output."
    panel(f"bash exit {result.returncode}", output.strip(), get_mode(config.mode), border_style="green" if result.returncode == 0 else "red")
    return config


def handle_web_search(args: list[str], root: Path, config: TurtlesConfig) -> TurtlesConfig:
    query = " ".join(args) or Prompt.ask("Search query")
    url = f"https://duckduckgo.com/html/?q={urllib.parse.quote_plus(query)}"
    with processing_animation("Searching web", get_mode(config.mode)):
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
    panel("Web search", "\n\n".join(lines) if lines else "No results found.", get_mode(config.mode))
    return config


def ai_or_error(config: TurtlesConfig, mode: TurtleMode, system: str, prompt: str) -> str:
    if not provider_ready(config):
        shell_problem("No AI provider/model is configured. Run /login, then /test-model.")
        return ""
    try:
        with processing_animation(
            "AI processing",
            mode,
            phases=["checking active provider", "preparing request", "waiting for model", "reading response"],
        ):
            response = complete_text(config, system, prompt)
        status(f"Used {response.provider} / {response.model}.", mode, style="green")
        return response.text
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
        return True, handler(args, root, config)
    except Exception as exc:  # noqa: BLE001 - interactive CLI should recover gracefully.
        shell_problem(str(exc))
        return True, config
