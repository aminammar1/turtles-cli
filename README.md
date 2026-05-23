# Turtles CLI

Project prep shell for coding assistants. Turtles CLI helps you audit a repo, shape prompts, manage provider login, test model connectivity, and scaffold assistant assets before handing work to tools like Claude, Codex, or Gemini.

## Install

```bash
uv sync --extra dev
uv run turtle
```

Run tests:

```bash
uv run --extra dev pytest
```

Run the local server:

```bash
uv run turtles-server --host 127.0.0.1 --port 8765
```

## First Use

```text
> /login
> /test-model
> /init
> /help
```

Credentials are stored per project in `.turtles/config.json`. Do not commit `.turtles/`.

## Core Commands

| Command | Purpose |
| --- | --- |
| `/login`, `/logout` | Configure or clear project-scoped provider credentials. |
| `/models` | List or switch the active model. |
| `/test-model` | Send a live request to verify provider/model connectivity. |
| `/init` | Create `.turtles/config.json` and `TURTLE.md` project instructions. |
| `/mode` | Switch turtle mode. |
| `/code-review` | Run local review heuristics. |
| `/security` | Scan for secrets and risky patterns. |
| `/docker` | Audit Dockerfile and Compose files. |
| `/context` | Estimate context window usage. |
| `/create-prompt` | Build a structured prompt. |
| `/enhance-prompt` | Improve a prompt with the configured model. |
| `/prompt-eval` | Evaluate prompt quality with the configured model. |
| `/simulation` | Ask the configured model for a scenario risk/plan/test assessment. |
| `/docs` | Create a custom instruction Markdown file, such as `database.md`, `design.md`, or `backend.md`. |
| `/skills` | List, install, or create project skills. |
| `/subagents` | List, install, or create project subagents. |
| `/plugins` | List, install, create, enable, or disable plugins. |
| `/mcp` | List, add, or check MCP servers. |
| `/github` | Choose git, GitHub CLI, and GitHub MCP actions. |
| `/web-search` | Search the web. |
| `/bash` | Run a shell command from the project root. |

AI-backed commands require `/login`; if the provider call fails, the CLI reports the error instead of pretending a local result is from the model. Commands that create custom generated content, such as `/docs`, use the active model.

## Providers

Supported login targets include OpenRouter, Anthropic, OpenAI, Google Gemini, NVIDIA AI, xAI, Azure OpenAI, Ollama, AWS Bedrock metadata, and custom OpenAI-compatible endpoints.

Use `/test-model` after `/login` to verify the selected model and credentials. The default example username is `user`; project-local config stores the actual name you choose.

## Assistant Assets

`create` is the only generation verb used by the CLI. It writes portable project assets:

```text
.claude/skills/<name>/SKILL.md
.codex/skills/<name>/SKILL.md
.gemini/skills/<name>/SKILL.md

.claude/agents/<name>.md
.codex/agents/<name>.md
.gemini/agents/<name>.md

plugins/<name>/.claude-plugin/plugin.json
plugins/<name>/.codex-plugin/plugin.json
plugins/<name>/.gemini-plugin/plugin.json
```

For Codex and Gemini, the CLI also updates project instruction files (`AGENTS.md` and `GEMINI.md`) with references to the created assets.

## Project Layout

```text
turtles_cli/
  main.py       # Typer entry point and shell loop
  commands.py   # Slash commands
  config.py     # Project config
  llm.py        # Provider clients
  providers.py  # Provider metadata
  scaffold.py   # Skills, subagents, plugins
  ui.py         # Rich terminal UI and animations
  mascots.py    # Turtle mascot frames
  audits.py     # Local scanners
  server.py     # FastAPI server

tests/
```

## Notes

- Runtime state lives in `.turtles/`.
- Local scanners do not need a model.
- Provider-backed commands do need a working model.
- MCP transport support is still early; `/mcp check-github` and `/github mcp-check` provide diagnostics.

## License

MIT
