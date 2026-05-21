from __future__ import annotations

import getpass
import html
import re
import subprocess
import urllib.parse
from pathlib import Path
from typing import Callable

import httpx
from rich import box
from rich.prompt import Confirm, Prompt
from rich.table import Table

from .audits import Finding, ai_detect, code_review, context_usage, docker_audit, security_audit
from .config import ProviderConfig, TurtlesConfig, init_project, is_logged_in, load_config, redacted_config, save_config
from .modes import TurtleMode, get_mode
from .prompting import choose_from_keyboard
from .prompts import enhance_prompt, evaluate_prompt, simulation_grade
from .providers import PROVIDERS
from .scaffold import create_plugin, create_skill, create_subagent
from .session import load_cache
from .ui import console, masked_prompt, panel, shell_problem, status


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


def handle_login(args: list[str], root: Path, config: TurtlesConfig) -> TurtlesConfig:
    providers = list(PROVIDERS.values())
    default_provider = PROVIDERS.get(config.provider.provider, PROVIDERS["openrouter"])
    provider_label = choose_from_keyboard("Provider", [provider.label for provider in providers], default=default_provider.label)
    provider = next(provider for provider in providers if provider.label == provider_label)
    username = Prompt.ask("Username", default=config.provider.username or getpass.getuser())
    secret_label = "Ollama host" if provider.key == "ollama" else f"{provider.label} API key"
    if provider.key == "ollama":
        api_key = Prompt.ask(secret_label, default="http://127.0.0.1:11434")
    else:
        api_key = masked_prompt(secret_label)
    model = choose_from_keyboard("Default model", list(provider.default_models), default=provider.default_models[0])
    config.provider = ProviderConfig(provider=provider.key, username=username, api_key=api_key, model=model)
    save_config(config, root)
    status(f"Logged in to {provider.label} for this project.", get_mode(config.mode), style="green")
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
    for index, model in enumerate(provider.default_models, start=1):
        table.add_row(str(index), model, "yes" if model == config.provider.model else "")
    console.print(table)
    if Confirm.ask("Switch model?", default=False):
        config.provider.model = choose_from_keyboard("Model", list(provider.default_models), default=config.provider.model or provider.default_models[0])
        save_config(config, root)
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
    action = choose_from_keyboard(f"{kind} action", ["list", "install", "create", "generate"], default="list")
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
        if kind == "skills":
            result = create_skill(root, name, description)
        else:
            result = create_subagent(root, name, description)
        collection.append(str(result.path.relative_to(root)))
        save_config(config, root)
        status(f"Created {result.kind}: {result.path.relative_to(root)}", mode)
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
        result = create_plugin(root, name, description, author=config.provider.username or "Turtles CLI user")
        config.plugins[str(result.path.parent.parent.relative_to(root))] = True
        save_config(config, root)
        status(f"Created plugin: {result.path.relative_to(root)}", get_mode(config.mode))
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
    init_project(root)
    status(f"Initialized {root / '.turtles' / 'config.json'}", get_mode(config.mode))
    return load_config(root)


def handle_docs(args: list[str], root: Path, config: TurtlesConfig) -> TurtlesConfig:
    target = root / "TURTLES.md"
    body = f"""# Turtles CLI Project Rules

Mode: {get_mode(config.mode).name}
Provider: {config.provider.provider or "not configured"}

## Scope
- Operate only inside this project folder.
- Keep credentials out of source control.
- Use `/security`, `/code-review`, `/prompt-eval`, and `/simulation` before handing work to a coding assistant.

## Workflow
- Start with project trust.
- Run audits before large changes.
- Prefer explicit prompts with files, constraints, tests, and expected output.
"""
    target.write_text(body, encoding="utf-8")
    status(f"Wrote {target}", get_mode(config.mode))
    return config


def handle_code_review(args: list[str], root: Path, config: TurtlesConfig) -> TurtlesConfig:
    target = args[0] if args else None
    print_findings(code_review(root, target), "Code Review", get_mode(config.mode))
    return config


def handle_security(args: list[str], root: Path, config: TurtlesConfig) -> TurtlesConfig:
    target = args[0] if args else None
    print_findings(security_audit(root, target), "Security Audit", get_mode(config.mode))
    return config


def handle_mcp(args: list[str], root: Path, config: TurtlesConfig) -> TurtlesConfig:
    action = args[0] if args else Prompt.ask("MCP action", choices=["list", "add-url", "add-stdio"], default="list")
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
    return config


def handle_mcp_suggestion(args: list[str], root: Path, config: TurtlesConfig) -> TurtlesConfig:
    suggestions = ["github: enabled by default for repository work"]
    if (root / "package.json").exists():
        suggestions.append("filesystem/search MCP for JS monorepo navigation")
    if (root / "pyproject.toml").exists():
        suggestions.append("python tooling MCP for package/test metadata")
    panel("MCP suggestions", "\n".join(suggestions), get_mode(config.mode))
    return config


def handle_docker(args: list[str], root: Path, config: TurtlesConfig) -> TurtlesConfig:
    print_findings(docker_audit(root), "Docker Audit", get_mode(config.mode))
    return config


def handle_api(args: list[str], root: Path, config: TurtlesConfig) -> TurtlesConfig:
    suggestions = [
        "GitHub REST/GraphQL API: repository automation and release workflows.",
        "OpenAPI-compatible public APIs: generate clients and validation from specs.",
        "Stack Exchange API: developer knowledge lookup for docs/support tools.",
    ]
    panel("API suggestions", "\n".join(suggestions), get_mode(config.mode))
    return config


def handle_ai(args: list[str], root: Path, config: TurtlesConfig) -> TurtlesConfig:
    suggestions = [
        "Ollama: local models such as Llama, Mistral, and Qwen Coder.",
        "OpenRouter: broad hosted model routing, including free/community tiers when available.",
        "Google AI Studio: Gemini models for prototyping.",
        "Hugging Face: open models and inference providers for experiments.",
    ]
    panel("AI options", "\n".join(suggestions), get_mode(config.mode))
    return config


def handle_github(args: list[str], root: Path, config: TurtlesConfig) -> TurtlesConfig:
    subcommand = args[0] if args else "status"
    commands = {
        "status": ["git", "status", "--short"],
        "branch": ["git", "branch", "--show-current"],
        "push": ["git", "push"],
    }
    if subcommand == "commit":
        message = " ".join(args[1:]) or Prompt.ask("Commit message")
        command = ["git", "add", "."] 
        subprocess.run(command, cwd=root, check=False)
        result = subprocess.run(["git", "commit", "-m", message], cwd=root, text=True, capture_output=True, check=False)
    elif subcommand == "pr":
        result = subprocess.run(["gh", "pr", "create", "--web"], cwd=root, text=True, capture_output=True, check=False)
    else:
        result = subprocess.run(commands.get(subcommand, ["git", subcommand]), cwd=root, text=True, capture_output=True, check=False)
    output = result.stdout or result.stderr or "No output."
    panel(f"github {subcommand}", output.strip(), get_mode(config.mode))
    return config


def handle_suggest(kind: str, args: list[str], root: Path, config: TurtlesConfig) -> TurtlesConfig:
    suggestions = {
        "skills": ["prompt-evaluation", "security-audit", "docker-hardening"],
        "plugins": ["github", "netlify", "hugging-face"],
        "subagents": ["reviewer", "security analyst", "prompt critic"],
    }
    panel(f"Suggested {kind}", "\n".join(suggestions[kind]), get_mode(config.mode))
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
    panel("Enhanced prompt", enhance_prompt(prompt), get_mode(config.mode))
    return config


def handle_prompt_eval(args: list[str], root: Path, config: TurtlesConfig) -> TurtlesConfig:
    prompt = " ".join(args) or Prompt.ask("Prompt")
    score, notes = evaluate_prompt(prompt)
    body = f"Clarity: {score.clarity}\nSpecificity: {score.specificity}\nSafety: {score.safety}\nOutput quality: {score.output_quality}\nTotal: {score.total}\n\n" + ("\n".join(notes) if notes else "Strong prompt shape.")
    panel("Prompt evaluation", body, get_mode(config.mode))
    return config


def handle_simulation(args: list[str], root: Path, config: TurtlesConfig) -> TurtlesConfig:
    console.print("[yellow]Important: a simulation scenario is just a prompt with optional skills, sub-agents, or plugins. It does not execute the work.[/yellow]")
    prompt = " ".join(args) or Prompt.ask("Scenario prompt")
    code_involved = Confirm.ask("Does this scenario involve code?", default=True)
    grade = simulation_grade(prompt, code_involved)
    body = "\n".join(f"{key}: {value}" for key, value in grade.items())
    panel("Simulation grade", body, get_mode(config.mode))
    return config


def handle_turtle_mode(args: list[str], root: Path, config: TurtlesConfig) -> TurtlesConfig:
    body = """Turtle Mode will simulate a multi-agent dance across the project:

- Leonardo coordinates strategy and acceptance criteria.
- Donatello maps architecture, dependencies, and tool choices.
- Raphael attacks risk, security, and regression hotspots.
- Michelangelo explores creative prompts and alternate workflows.

Interface stub:
1. Select roles.
2. Assign project slices.
3. Run parallel evaluations.
4. Merge findings into a single workflow report.

# TODO: implement multi-agent orchestration in a future release."""
    panel("Turtle Mode", body, get_mode(config.mode))
    return config


def handle_help(args: list[str], root: Path, config: TurtlesConfig) -> TurtlesConfig:
    table = Table(title="Turtles CLI Commands", box=box.SIMPLE_HEAVY, header_style="bold green")
    table.add_column("Command")
    table.add_column("Purpose")
    commands = {
        "/login": "Configure project-scoped provider credentials.",
        "/models": "List and switch models for the active provider.",
        "/provider": "Switch provider or re-authenticate.",
        "/customize-cli": "Change prompt style, theme, verbosity, and animation.",
        "/skills": "Install or generate skills.",
        "/subagents": "Install or generate sub-agents.",
        "/hooks": "Manage lifecycle hooks.",
        "/plugins": "Install, enable, or disable plugins.",
        "/init": "Initialize .turtles/config.json.",
        "/docs": "Generate TURTLES.md project rules.",
        "/code-review": "Run local code review heuristics.",
        "/security": "Scan for secrets and risky patterns.",
        "/mcp": "List or add MCP servers. GitHub MCP is enabled by default.",
        "/mcp-suggestion": "Suggest relevant MCP servers.",
        "/docker": "Audit Dockerfile and Compose files.",
        "/api": "Suggest relevant APIs.",
        "/AI": "Suggest open/free AI providers and models.",
        "/github": "Run GitHub-oriented git/gh operations.",
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
    estimate, findings = ai_detect(root)
    print_findings(findings, f"AI Detection Estimate: {estimate}%", get_mode(config.mode))
    return config


def handle_context(args: list[str], root: Path, config: TurtlesConfig) -> TurtlesConfig:
    cache = load_cache(root)
    segments = args if args else cache.context_segments
    usage = context_usage(segments)
    body = "\n".join(f"{key}: {value}" for key, value in usage.items())
    if cache.recent_commands:
        body += "\n\nRecent commands:\n" + "\n".join(cache.recent_commands[-8:])
    panel("Context usage estimate", body, get_mode(config.mode))
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
            return config
    return config


def handle_bash(args: list[str], root: Path, config: TurtlesConfig) -> TurtlesConfig:
    command = " ".join(args) or Prompt.ask("bash")
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


HANDLERS: dict[str, CommandHandler] = {
    "/login": handle_login,
    "/models": handle_models,
    "/provider": handle_provider,
    "/customize-cli": handle_customize,
    "/skills": lambda args, root, config: handle_simple_registry("skills", args, root, config),
    "/subagents": lambda args, root, config: handle_simple_registry("subagents", args, root, config),
    "/hooks": handle_hooks,
    "/plugins": handle_plugins,
    "/init": handle_init,
    "/docs": handle_docs,
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
