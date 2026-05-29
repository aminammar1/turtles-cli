# 🐢 Turtles CLI

**Project prep shell for coding assistants.**

Turtles CLI is an interactive terminal tool that gets your repo ready before handing work off to AI coding assistants like Claude, Codex, or Gemini. It handles provider auth, model testing, context estimation, code review, security scanning, and asset scaffolding all from a single shell.

---

## Contents

- [Features](#features)
- [Prerequisites](#prerequisites)
- [Installation](#installation)
- [Quick Start](#quick-start)
- [Commands](#commands)
- [Providers](#providers)
- [Assistant Assets](#assistant-assets)
- [GitHub MCP Integration](#github-mcp-integration)
- [Project Structure](#project-structure)
- [Configuration](#configuration)
- [License](#license)

---

## Features

- 🔐 **Provider auth** — scoped per project, not globally
- 🤖 **Multi-provider support** — Anthropic, OpenAI, Gemini, Ollama, Azure, AWS, and more
- 🔍 **Code quality tools** — review heuristics, secret scanning, Dockerfile audits
- 💬 **Prompt workflows** — build, enhance, and evaluate prompts against a live model
- 📦 **Asset scaffolding** — generate skills, subagents, and plugins for Claude, Codex, and Gemini
- 🔗 **MCP integration** — configure and diagnose GitHub MCP servers
- 💡 **Interactive shell** — plain chat with `@path` file references and tab completion

---

## Prerequisites

- Python 3.11+
- [`uv`](https://github.com/astral-sh/uv) package manager

---

## Installation

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

---

## Quick Start

```text
> /login          # Connect your provider and set credentials
> /test-model     # Verify connectivity with a live request
> /init           # Create .turtles/config.json and TURTLE.md
> /help           # Show all available commands
```

Credentials are stored per project in `.turtles/config.json`. **Do not commit `.turtles/` to version control.**

---

## Commands

### Setup & Auth

| Command | Description |
|---|---|
| `/login` | Configure project-scoped provider credentials |
| `/logout` | Clear stored credentials |
| `/models` | List available models or switch the active one |
| `/test-model` | Send a live request to verify provider and model connectivity |

### Project Initialization

| Command | Description |
|---|---|
| `/init` | Create `.turtles/config.json` and `TURTLE.md` project instructions |
| `/mode` | Switch turtle mode with a visual CLI preview |
| `/context` | Estimate current context window usage |

### Code Quality

| Command | Description |
|---|---|
| `/code-review` | Run local review heuristics, then ask the model to prioritize findings |
| `/security` | Scan for secrets and risky patterns, then ask the model to assess risk |
| `/docker` | Audit Dockerfile and Compose files, then ask the model for fixes |

### Prompt Engineering

| Command | Description |
|---|---|
| `/create-prompt` | Build a structured prompt interactively |
| `/enhance-prompt` | Improve a prompt using the configured model |
| `/prompt-eval` | Evaluate prompt quality with the configured model |
| `/simulation` | Ask the model for a scenario risk/plan/test assessment. Supports `@path` references |

### Assets & Documentation

| Command | Description |
|---|---|
| `/docs` | Create a custom instruction Markdown file (e.g. `database.md`, `backend.md`) |
| `/skills` | List, install, or create project skills |
| `/subagents` | List, install, or create project subagents |
| `/plugins` | List, install, create, enable, or disable plugins |

### Integrations & Utilities

| Command | Description |
|---|---|
| `/mcp` | List, add, or check MCP servers |
| `/github` | Choose git, GitHub CLI, and GitHub MCP actions |
| `/web-search` | Search the web |
| `/bash` | Run a shell command from the project root |

> **Note:** AI-backed commands require `/login`. If a provider call fails, the CLI reports the error directly — it never substitutes a local result as if it came from the model. Setup and utility commands (`/login`, `/logout`, `/mode`, `/help`, `/bash`, `/github`, `/web-search`, `/mcp list`, `/mcp check-github`) always run locally.

---

## Providers

Turtles CLI supports logging in to the following providers:

| Provider | Notes |
|---|---|
| Anthropic | Claude model family |
| OpenAI | GPT model family |
| OpenRouter | Unified API for many providers |
| Google Gemini | Gemini model family |
| NVIDIA AI | NVIDIA-hosted models |
| xAI | Grok model family |
| Azure OpenAI | Azure-hosted OpenAI models |
| Ollama | Local model inference |
| AWS Bedrock | Metadata-based login |
| Custom endpoint | Any OpenAI-compatible API |

After logging in, always run `/test-model` to confirm your selected model and credentials are working.

---

## Assistant Assets

The `/skills`, `/subagents`, and `/plugins` commands scaffold portable project assets using `create` as the single generation verb. Output paths follow each assistant's conventions:

**Skills**
```
.claude/skills/<name>/SKILL.md
.codex/skills/<name>/SKILL.md
.gemini/skills/<name>/SKILL.md
```

**Subagents / Agents**
```
.claude/agents/<name>.md
.codex/agents/<name>.md
.gemini/agents/<name>.md
```

**Plugins**
```
plugins/<name>/.claude-plugin/plugin.json
plugins/<name>/.codex-plugin/plugin.json
plugins/<name>/.gemini-plugin/plugin.json
```

For Codex and Gemini, the CLI also updates the relevant project instruction files (`AGENTS.md` and `GEMINI.md`) with references to newly created assets.

---

## GitHub MCP Integration

Turtles CLI expects a project MCP server named `github`, configured with the stdio command `github-mcp-server` by default.

**Test the GitHub MCP server:**

```text
> /mcp check-github
```

The diagnostic checks whether the server is configured and enabled, whether the executable is on `PATH`, whether `GITHUB_TOKEN` is set, and whether the command responds to `--help`.

**Use a different executable:**

```text
> /mcp add-stdio
Server name: github
stdio command: <your github mcp server command>

> /mcp check-github
```

> MCP transport support is still early. `/mcp check-github` and `/github mcp-check` are the recommended diagnostic commands.

---

## Turtle Mode

> ⚠️ **Experimental** — Turtle Mode is an experimental multi-agent orchestration feature. **Test with simple, non-destructive prompts only.** The goal is to observe what happens when multiple AI code assistants work on the same project simultaneously.

Turtle Mode connects to multiple machines (your local machine + remote EC2 instances), detects which code assistant CLIs are installed, sends the **same prompt** to two agents at the same time, streams both responses side-by-side, and then asks an AI to grade how they collaborated.

### How It Works

```
/turtle-mode
  │
  ├─ 🔗 Phase 1: Connect
  │    SSH into remote machines + local machine
  │    Ping each connection to verify
  │
  ├─ 🔍 Phase 2: Detect Agents
  │    Scan for: gemini-cli, claude-code, agy, codex, opencode
  │    Pick which agent to use on each machine
  │
  ├─ 📝 Phase 3: Execute
  │    Type one prompt → sent to both agents simultaneously
  │    Responses stream back in a split-panel view
  │
  └─ 🏆 Phase 4: Grade
       AI analyzes coherence, conflicts, complementarity
       Collaboration score + recommendation
```

### Prerequisites

- At least **2 machines** with a code assistant CLI installed (e.g. `gemini`, `claude`, `agy`, `codex`, or `opencode`)
- SSH access to remote machines (key-based authentication recommended)
- The **same project** checked out on all machines (via git clone)
- A configured AI provider (`/login`) for the grading phase

### Configuration

On first run, `/turtle-mode` will prompt you for remote machine details:

```text
Machine name: ec2-agent-1
Host (IP or hostname): 54.123.45.67
SSH user: ubuntu
SSH key path: ~/.ssh/my-key.pem
SSH port: 22
Remote project path: /home/ubuntu/my-project
```

Machine configurations are saved in `.turtles/config.json` and reused on subsequent runs.

### Supported Code Assistants

| Agent | Binary | One-Shot Command |
|---|---|---|
| Gemini CLI | `gemini` | `gemini -p "prompt"` |
| Claude Code | `claude` | `claude -p "prompt"` |
| Antigravity SDK | `agy` | `agy run "prompt"` |
| Codex CLI | `codex` | `codex "prompt"` |
| OpenCode | `opencode` | `opencode "prompt"` |

### ⚠️ Important Warnings

- **Start simple**: Use read-only prompts first (e.g. "explain main.py") before trying write operations
- **Conflict risk**: Two agents editing the same files simultaneously **will** cause conflicts
- **Not production-ready**: This is a research/experimentation tool to study multi-agent behavior
- **Resource usage**: Running two AI agents simultaneously uses more API credits and compute

---

## Project Structure

```
turtles_cli/
  main.py         # Typer entry point and shell loop
  commands.py     # Slash commands
  config.py       # Project config
  llm.py          # Provider clients
  providers.py    # Provider metadata
  scaffold.py     # Skills, subagents, plugins
  ui.py           # Rich terminal UI and animations
  mascots.py      # Turtle mascot frames
  audits.py       # Local scanners
  remote.py       # SSH connection manager for turtle-mode
  turtle_mode.py  # Multi-agent orchestration
  server.py       # FastAPI server

tests/
```

Runtime state lives in `.turtles/`.

---

## Configuration

Project configuration is stored in `.turtles/config.json` after running `/init`. This file holds your provider credentials, active model selection, and project metadata. The default example username is `user`; the actual name you choose is stored locally and never shared.

**Do not commit `.turtles/` to your repository.**

---

## License

[MIT](LICENSE)