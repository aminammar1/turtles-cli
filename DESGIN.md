# Turtles CLI Design Guide

## Architecture Overview

Turtles CLI follows a modular, layered architecture designed for extensibility and team collaboration.

### Core Components

```
turtles_cli/
├── main.py          # Entry point, CLI routing
├── commands.py      # Command implementations
├── config.py        # Configuration management
├── session.py       # Session state handling
├── llm.py           # LLM abstraction layer
├── providers.py     # LLM provider integrations
├── prompting.py     # Prompt engineering utilities
├── prompts.py       # Prompt templates
├── modes.py         # Operational modes
├── scaffold.py      # Project scaffolding
├── ui.py            # Terminal UI components
└── mascots.py       # Branding/ASCII art
```

## Design Principles

### 1. Separation of Concerns
- **Commands**: User-facing operations, thin wrappers
- **Providers**: LLM API integrations, swappable
- **Session**: State management, persistence
- **UI**: Presentation layer, no business logic

### 2. Configuration Flow
```
CLI Args → Config File → Environment → Defaults
```
- Priority: CLI flags override config file, which overrides env vars
- Config stored in `~/.turtles/config.yaml` or project `.turtles.yaml`

### 3. Provider Abstraction
```python
# All providers implement common interface
class LLMProvider(Protocol):
    def complete(self, messages: List[dict]) -> str
    def stream(self, messages: List[dict]) -> Iterator[str]
```
- Supports: OpenAI, Anthropic, Ollama, custom endpoints
- Easy to add new providers by implementing the protocol

### 4. Session Management
- Each interaction creates a session with unique ID
- Sessions track: messages, metadata, artifacts
- Stored in `~/.turtles/sessions/` for persistence

## Extension Guide

### Adding a New Command
1. Add function to `commands.py`
2. Register in `main.py` with `@app.command()`
3. Add tests in `tests/test_commands.py`

### Adding a New Provider
1. Implement `LLMProvider` protocol in `providers.py`
2. Add to provider factory in `llm.py`
3. Update config schema in `config.py`

### Adding Prompt Templates
1. Add template to `prompts.py`
2. Reference in `prompting.py` functions
3. Document in README.md

## Testing Strategy
- Unit tests for each module
- Integration tests for provider connections
- CLI tests via subprocess invocation
- Run: `make test`

## Common Patterns

### Error Handling
```python
try:
    result = provider.complete(messages)
except ProviderError as e:
    ui.error(f"LLM error: {e}")
    raise typer.Exit(1)
```

### Logging
- Use `loguru` for structured logging
- Debug logs to file, errors to stderr
- Respect `--verbose` flag

### Async Support
- Use `asyncio` for I/O-bound operations
- Stream responses for better UX
- Run async code in thread pool when needed
