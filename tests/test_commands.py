from turtles_cli.commands import dispatch, github_mcp_diagnostics
from turtles_cli.config import ProviderConfig, TurtlesConfig, load_config


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
    assert updated.trusted is False


def test_github_mcp_diagnostics_reports_configuration() -> None:
    body = github_mcp_diagnostics(TurtlesConfig())

    assert "configured: yes" in body
    assert "command: github-mcp-server" in body
