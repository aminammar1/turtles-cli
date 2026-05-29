from turtles_cli.audits import Finding, ai_detect
from turtles_cli.commands import (
    ai_or_error,
    ai_tool_context,
    command_path_arg,
    dispatch,
    extract_file_mentions,
    github_mcp_diagnostics,
    project_read_context,
    response_has_fake_tool_call,
    response_is_malformed,
    scanner_prompt,
    setup_github_mcp,
)
from turtles_cli.config import ProviderConfig, TurtlesConfig, load_config
from turtles_cli.llm import LLMResponse
from turtles_cli.modes import get_mode


def test_logout_clears_project_credentials(tmp_path) -> None:
    config = TurtlesConfig(provider=ProviderConfig(provider="openai", api_key="sk-test", model="gpt-5.2"))

    should_continue, updated = dispatch("/logout", tmp_path, config)
    loaded = load_config(tmp_path)

    assert should_continue is True
    assert updated.provider.provider == ""
    assert loaded.provider.api_key == ""


def test_plain_prompt_without_provider_uses_local_guidance(tmp_path) -> None:
    should_continue, updated = dispatch("explain this repo", tmp_path, TurtlesConfig())

    assert should_continue is True
    assert updated.provider.provider == ""


def test_test_model_command_requires_login(tmp_path) -> None:
    should_continue, updated = dispatch("/test-model", tmp_path, TurtlesConfig())

    assert should_continue is True
    assert updated.provider.provider == ""


def test_init_creates_turtle_markdown_instructions(tmp_path) -> None:
    should_continue, updated = dispatch("/init", tmp_path, TurtlesConfig())

    assert should_continue is True
    assert (tmp_path / ".turtles" / "config.json").exists()
    assert (tmp_path / "TURTLE.md").exists()
    assert "local Turtles CLI init template" in (tmp_path / "TURTLE.md").read_text(encoding="utf-8")
    assert updated.trusted is False


def test_init_uses_ai_when_provider_is_ready(tmp_path, monkeypatch) -> None:
    config = TurtlesConfig(provider=ProviderConfig(provider="openai", api_key="sk-test", model="gpt-test"))

    def fake_complete(_config, _system, _prompt, **_kwargs):
        return LLMResponse("# TURTLE.md\n\n> Source: active AI provider/model via Turtles CLI\n", "OpenAI", "gpt-test")

    monkeypatch.setattr("turtles_cli.commands.complete_text", fake_complete)

    should_continue, _updated = dispatch("/init", tmp_path, config)

    assert should_continue is True
    assert "active AI provider/model" in (tmp_path / "TURTLE.md").read_text(encoding="utf-8")


def test_docs_requires_ai_before_writing(tmp_path) -> None:
    should_continue, updated = dispatch("/docs backend keep database notes", tmp_path, TurtlesConfig())

    assert should_continue is True
    assert updated.provider.provider == ""
    assert not (tmp_path / "backend.md").exists()


def test_github_mcp_diagnostics_reports_configuration() -> None:
    body = github_mcp_diagnostics(TurtlesConfig())

    assert "configured: yes" in body
    assert "command: github-mcp-server" in body


def test_extract_file_mentions_for_simulation_context() -> None:
    mentions = extract_file_mentions("Review @.codex/skills/demo/SKILL.md and @plugins/demo")

    assert mentions == [".codex/skills/demo/SKILL.md", "plugins/demo"]


def test_command_path_arg_accepts_file_mentions() -> None:
    assert command_path_arg("@turtles_cli/commands.py") == "turtles_cli/commands.py"
    assert command_path_arg("turtles_cli/commands.py") == "turtles_cli/commands.py"
    assert command_path_arg(None) is None


def test_ai_tool_context_reads_project_mentions(tmp_path) -> None:
    target = tmp_path / "TURTLE.md"
    target.write_text("Use skills and plugins carefully.\n", encoding="utf-8")

    body = ai_tool_context(tmp_path, "Simulate @TURTLE.md", TurtlesConfig())

    assert "bash snapshot:" in body
    assert "@TURTLE.md file contents:" in body
    assert "Use skills and plugins carefully." in body


def test_project_read_context_reads_instruction_files_first(tmp_path) -> None:
    (tmp_path / "app.py").write_text("print('app')\n", encoding="utf-8")
    (tmp_path / "TURTLE.md").write_text("Follow project instructions first.\n", encoding="utf-8")

    body = project_read_context(tmp_path)

    assert "read phase 1: instruction files found and read first:" in body
    assert body.index("--- TURTLE.md ---") < body.index("--- app.py ---")


def test_project_read_context_reads_project_files_without_instruction_file(tmp_path) -> None:
    (tmp_path / "app.py").write_text("print('app')\n", encoding="utf-8")

    body = project_read_context(tmp_path)

    assert "no instruction files found" in body
    assert "--- app.py ---" in body


def test_scanner_prompt_includes_finding_linked_snippets(tmp_path) -> None:
    source = tmp_path / "app.py"
    source.write_text("one\nproblem_line()\nthree\n", encoding="utf-8")

    body = scanner_prompt(tmp_path, "code review", [Finding("app.py", 2, "high", "Problem found.")])

    assert "Project read context:" in body
    assert "Finding-linked snippets:" in body
    assert "Finding-linked file reads:" in body
    assert "> 2: problem_line()" in body
    assert "--- app.py ---" in body


def test_ai_detect_does_not_flag_plain_tool_mentions(tmp_path) -> None:
    source = tmp_path / "README.md"
    source.write_text("This project can use Copilot or Windsurf as editor integrations.\n", encoding="utf-8")

    estimate, findings = ai_detect(tmp_path)

    assert estimate == 0
    assert findings == []


def test_setup_github_mcp_creates_docker_wrapper(tmp_path, monkeypatch) -> None:
    config = TurtlesConfig()

    def fake_which(name: str) -> str | None:
        return None if name == "github-mcp-server" else "/usr/bin/docker" if name == "docker" else None

    monkeypatch.setattr("turtles_cli.commands.shutil.which", fake_which)

    body = setup_github_mcp(tmp_path, config)

    assert "created docker wrapper" in body
    assert config.mcp_servers["github"]["command"] == ".turtles/github-mcp-server"
    assert (tmp_path / ".turtles" / "github-mcp-server").exists()


def test_ai_or_error_repairs_fake_tool_call_response(tmp_path, monkeypatch) -> None:
    config = TurtlesConfig(provider=ProviderConfig(provider="openai", api_key="sk-test", model="gpt-test"))
    calls: list[str] = []

    def fake_complete(_config, _system, prompt, **_kwargs):
        calls.append(prompt)
        if len(calls) == 1:
            return LLMResponse(
                "I'll inspect the file. <tool_call>bash execute: \"sed -n '1,20p' app.py\"</tool_call>",
                "OpenAI",
                "gpt-test",
            )
        return LLMResponse("Final report from supplied evidence only.", "OpenAI", "gpt-test")

    monkeypatch.setattr("turtles_cli.commands.complete_text", fake_complete)

    body = ai_or_error(config, get_mode("leonardo"), "Review evidence.", "Finding summary.", root=tmp_path)

    assert len(calls) == 2
    assert body == "Final report from supplied evidence only."
    assert response_has_fake_tool_call(calls[1])


def test_ai_or_error_repairs_malformed_plain_prompt(tmp_path, monkeypatch) -> None:
    config = TurtlesConfig(provider=ProviderConfig(provider="openai", api_key="sk-test", model="gpt-test"))
    calls: list[str] = []

    def fake_complete(_config, _system, prompt, **_kwargs):
        calls.append(prompt)
        if len(calls) == 1:
            return LLMResponse("```python\nprint('not a prompt')\n```", "OpenAI", "gpt-test")
        return LLMResponse("## Goal\nWrite a focused review prompt.", "OpenAI", "gpt-test")

    monkeypatch.setattr("turtles_cli.commands.complete_text", fake_complete)

    body = ai_or_error(config, get_mode("leonardo"), "Create prompt.", "Goal: review", root=tmp_path, output_contract="plain_prompt")

    assert len(calls) == 2
    assert body.startswith("## Goal")
    assert response_is_malformed("```python\nprint('x')\n```", "plain_prompt")


def test_github_status_does_not_require_ai(tmp_path) -> None:
    should_continue, updated = dispatch("/github status", tmp_path, TurtlesConfig())

    assert should_continue is True
    assert updated.provider.provider == ""


def test_bash_does_not_require_ai(tmp_path) -> None:
    should_continue, updated = dispatch("/bash printf ok", tmp_path, TurtlesConfig())

    assert should_continue is True
    assert updated.provider.provider == ""
