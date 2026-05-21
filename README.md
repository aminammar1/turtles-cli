# Turtles CLI

Turtles CLI is a developer pre-tool for the work that happens before you hand a project to a coding assistant. It prepares, audits, evaluates, scaffolds, and optimizes the project context so your main assistant starts with cleaner inputs and fewer surprises.

It is inspired by the terminal-first interaction style of Claude Code, OpenAI Codex CLI, and Aider, but it is not a coding agent. Turtles CLI does not ship models or write your application for you. It gives you project-scoped workflow tools, local scanners, prompt utilities, MCP configuration, and a dark terminal UI with Ninja Turtles personality modes.

This project is 100% open source. Contributions, issues, experiments, docs fixes, integrations, and community help are very welcome.

## Features

- `turtle` startup flow with an animated four-mask ASCII wordmark and `TURTLES CLI` shell header.
- Project trust prompt before any project action.
- Color-coded turtle modes:
  - Leonardo, blue: balanced planning.
  - Donatello, purple: deep technical analysis.
  - Raphael, red: fast audits and blunt feedback.
  - Michelangelo, orange: creative prompt exploration.
- Rich terminal UI with Claude-like `>` input and clean status lines.
- Prompt-toolkit command input with command autocomplete, completion menu, persistent history, and keyboard navigation.
- Local project config in `.turtles/config.json`.
- Local session cache in `.turtles/cache.json` and command history in `.turtles/history`, so mode, login, model, recent commands, and context estimates survive restarts.
- Local FastAPI server with REST endpoints and an MCP-style tool listing.
- Provider login flow for OpenRouter, Anthropic, OpenAI, Google Gemini, AWS Bedrock, NVIDIA AI, xAI, Azure OpenAI, and Ollama.
- Project-level commands for reviews, security scans, Docker checks, prompt creation/evaluation, simulations, MCP management, GitHub operations, hooks, plugins, skills, and sub-agents.
- Claude-compatible scaffolding:
  - `/skills create` writes `.claude/skills/<name>/SKILL.md`
  - `/subagents create` writes `.claude/agents/<name>.md`
  - `/plugins create` writes `plugins/<name>/.claude-plugin/plugin.json` plus plugin `skills/`, `agents/`, `hooks/`, and `bin/`
- `/turtle-mode` interface stub with a clear future-release TODO.

## Install

This project uses `uv`.

```bash
uv sync --extra dev
uv run turtle
```

Run the local server:

```bash
uv run turtles-server --port 8765
```

Then visit:

```text
http://127.0.0.1:8765/health
```

## First Run

```bash
uv run turtle
```

The CLI will:

1. Play a short ASCII turtle animation.
2. Render the `TURTLES CLI` title.
3. Ask: `⚠ Trust this project folder? [y/N]`.
4. Let you choose a turtle mode.
5. Open the interactive shell.

Inside the shell:

```text
> /help
> /login
> /mode
> /code-review
> /security
> /bash git status --short
> /web-search model context protocol server examples
> /simulation Refactor the auth module and add tests
> /exit
```

## Commands

| Command | Purpose |
| --- | --- |
| `/login` | Configure project-scoped provider credentials. |
| `/models` | List and switch active provider models. |
| `/provider` | Switch provider or re-authenticate. |
| `/mode` | Switch turtle mode with keyboard autocomplete. |
| `/customize-cli` | Change prompt style, color theme, verbosity, and display preferences. |
| `/skills` | Install a skill from GitHub or generate a skill draft from a description. |
| `/subagents` | Install or generate sub-agent definitions. |
| `/hooks` | Configure lifecycle hooks such as pre-commit and pre-push. |
| `/plugins` | Install, enable, or disable plugins. |
| `/init` | Create `.turtles/config.json` for the current project. |
| `/docs` | Generate `TURTLES.md` project rules. |
| `/code-review` | Run local code review heuristics for the project or a target path. |
| `/security` | Scan for possible secrets and unsafe patterns. |
| `/mcp` | List or add MCP servers. GitHub MCP is enabled by default. |
| `/mcp-suggestion` | Suggest useful MCP servers based on project files. |
| `/docker` | Inspect Dockerfile and Compose files. |
| `/api` | Suggest relevant public/open APIs. |
| `/AI` | Suggest free or open AI models and providers. |
| `/github` | Run GitHub-style git and `gh` operations. |
| `/suggest-skills` | Suggest useful skills for the project. |
| `/suggest-plugins` | Suggest useful plugins. |
| `/suggest-subagents` | Suggest helpful sub-agents. |
| `/create-prompt` | Guided prompt creation flow. |
| `/enhance-prompt` | Improve an existing prompt. |
| `/prompt-eval` | Score prompt clarity, specificity, safety, and output quality. |
| `/simulation` | Grade an expected AI scenario before running it elsewhere. |
| `/turtle-mode` | Future multi-agent orchestration stub. |
| `/ai-detect` | Estimate AI-generated content markers in the project. |
| `/context` | Estimate context window usage. |
| `/bash` | Run a shell command from the project root. |
| `/web-search` | Search the web for project research. `/search` is an alias. |
| `/help` | Show command help. |

## Architecture

```text
turtles_cli/
  main.py       # Typer entry point and interactive shell
  ui.py         # Rich rendering, animation, mode picker
  commands.py   # Slash command dispatch and command handlers
  config.py     # Project-scoped configuration
  providers.py  # Provider metadata and model defaults
  audits.py     # Local review/security/Docker/AI-marker scanners
  prompts.py    # Prompt enhancement, evaluation, and simulation scoring
  scaffold.py   # Claude-compatible skill, subagent, and plugin scaffolds
  server.py     # FastAPI REST server and MCP-style tools endpoint
```

## Extension Standards

Turtles CLI creates project-level extension files that match the Claude Code ecosystem layout:

```text
.claude/
  skills/
    security-audit/
      SKILL.md
      examples/
      scripts/
  agents/
    code-reviewer.md

plugins/
  workflow-pack/
    .claude-plugin/
      plugin.json
    skills/
      review/
        SKILL.md
    agents/
      reviewer.md
    hooks/
      hooks.json
    bin/
```

Skills use `SKILL.md` with YAML frontmatter and Markdown instructions. Subagents use Markdown files with YAML frontmatter. Plugins use a `.claude-plugin/plugin.json` manifest and keep `skills/`, `agents/`, `hooks/`, and `bin/` at the plugin root.

The CLI is intentionally project-level only. It uses the current working directory as its root, ignores common dependency/build folders, and stores runtime state under `.turtles/`.

## Credentials

Turtles CLI does not provide model access. Bring your own provider and API key with `/login`.

Credentials are stored in the project-scoped `.turtles/config.json`, and `.turtles/` is ignored by git by default. The file is created with restrictive permissions where the platform supports it. For team use, prefer environment variables or a future secret-store integration rather than committing credentials.

On later launches, the CLI resumes the trusted project, selected turtle mode, active provider, and active model automatically. Use `/mode`, `/provider`, or `/models` to change them.

## Autocomplete

Interactive input uses a Claude/Codex-like command prompt:

- Type `/` to see slash-command suggestions.
- Use Tab to complete.
- Use Up/Down for history and completion menu navigation.
- Use `?` for shortcuts.
- Use Ctrl-D to exit.

Provider, model, and mode pickers also support typing partial names and Tab completion.

## Model Defaults

Default provider model lists are kept as current aliases or recent model IDs where possible:

- OpenAI: GPT-5.2 family and GPT-OSS.
- Anthropic: Claude Sonnet 4.6, Opus 4.7, Haiku 4.5.
- Google Gemini: Gemini 3 Pro preview and Gemini 2.5 models.
- xAI: Grok 4.3.
- NVIDIA: current Nemotron/NIM catalog models.
- Ollama: current popular local model families such as Qwen3, Llama 4 Scout, DeepSeek-R1, and Gemma 3.
- OpenRouter: routes to current cross-provider model slugs; OpenRouter also exposes a live models API for future dynamic refresh.

## Local Server

The server exposes local REST endpoints:

- `GET /health`
- `GET /config`
- `GET /review`
- `GET /security`
- `GET /docker`
- `GET /ai-detect`
- `POST /prompt-eval`
- `POST /simulation`
- `GET /mcp/tools`

The `/mcp/tools` endpoint is an MCP-style discovery surface for the built-in project tools. Full MCP transport implementations are planned.

## Current Status

This is an MVP scaffold with real local command routing, local scanners, prompt scoring, config persistence, and server endpoints. Provider-backed AI calls, marketplace registries, full MCP transports, and full Turtle Mode orchestration are intentionally left for future releases.

## Inspiration

- [Claude Code docs](https://docs.anthropic.com/en/docs/claude-code/overview)
- [OpenAI Codex CLI](https://github.com/openai/codex)
- [Aider](https://github.com/paul-gauthier/aider)
- [Rich](https://github.com/Textualize/rich)
- [Textual](https://github.com/Textualize/textual)
- [uv](https://github.com/astral-sh/uv)
- [Model Context Protocol](https://modelcontextprotocol.io/docs)
- [GitHub MCP server](https://github.com/github/github-mcp-server)
- [OpenRouter quickstart](https://openrouter.ai/docs/quick-start)
- [Prompt Engineering Guide](https://www.promptingguide.ai/)
- [Building effective agents](https://www.anthropic.com/research/building-effective-agents)

## Contributing

Open issues, send pull requests, propose turtle modes, add scanners, improve docs, or wire in new providers. The project is meant to be community-shaped.

Good first contribution ideas:

- Add a real provider client for one provider.
- Expand Docker and security checks.
- Add a plugin registry format.
- Implement MCP stdio transport.
- Add Textual screens for richer mode selection.
- Improve `/simulation` with model-backed scoring.

## License

MIT
