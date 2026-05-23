import json

from turtles_cli.scaffold import create_plugin, create_skill, create_subagent


def test_create_skill_uses_claude_skill_structure(tmp_path) -> None:
    result = create_skill(tmp_path, "Security Audit", "Audit secrets and risky code")

    assert result.path == tmp_path / ".claude" / "skills" / "security-audit" / "SKILL.md"
    assert "description: Audit secrets" in result.path.read_text(encoding="utf-8")
    assert (tmp_path / ".codex" / "skills" / "security-audit" / "SKILL.md").exists()
    assert (tmp_path / ".gemini" / "skills" / "security-audit" / "SKILL.md").exists()
    assert "security-audit" in (tmp_path / "AGENTS.md").read_text(encoding="utf-8")
    assert "security-audit" in (tmp_path / "GEMINI.md").read_text(encoding="utf-8")


def test_create_skill_can_target_codex_only(tmp_path) -> None:
    result = create_skill(tmp_path, "Security Audit", "Audit secrets and risky code", target="codex")

    assert result.path == tmp_path / ".codex" / "skills" / "security-audit" / "SKILL.md"
    assert (tmp_path / ".codex" / "skills" / "security-audit" / "SKILL.md").exists()
    assert not (tmp_path / ".claude" / "skills" / "security-audit" / "SKILL.md").exists()
    assert not (tmp_path / ".gemini" / "skills" / "security-audit" / "SKILL.md").exists()
    assert (tmp_path / "AGENTS.md").exists()
    assert not (tmp_path / "GEMINI.md").exists()


def test_create_subagent_uses_claude_agent_structure(tmp_path) -> None:
    result = create_subagent(tmp_path, "Code Reviewer", "Review diffs")

    assert result.path == tmp_path / ".claude" / "agents" / "code-reviewer.md"
    assert "tools:" in result.path.read_text(encoding="utf-8")
    assert (tmp_path / ".codex" / "agents" / "code-reviewer.md").exists()
    assert (tmp_path / ".gemini" / "agents" / "code-reviewer.md").exists()


def test_create_plugin_uses_plugin_manifest_structure(tmp_path) -> None:
    result = create_plugin(tmp_path, "Workflow Pack", "Reusable workflow helpers")
    manifest = json.loads(result.path.read_text(encoding="utf-8"))

    assert result.path == tmp_path / "plugins" / "workflow-pack" / ".claude-plugin" / "plugin.json"
    assert manifest["name"] == "workflow-pack"
    assert (tmp_path / "plugins" / "workflow-pack" / ".codex-plugin" / "plugin.json").exists()
    assert (tmp_path / "plugins" / "workflow-pack" / ".gemini-plugin" / "plugin.json").exists()
    assert (tmp_path / "plugins" / "workflow-pack" / "skills" / "review" / "SKILL.md").exists()


def test_create_plugin_can_target_gemini_only(tmp_path) -> None:
    result = create_plugin(tmp_path, "Workflow Pack", "Reusable workflow helpers", target="gemini")

    assert result.path == tmp_path / "plugins" / "workflow-pack" / ".gemini-plugin" / "plugin.json"
    assert not (tmp_path / "plugins" / "workflow-pack" / ".claude-plugin" / "plugin.json").exists()
    assert not (tmp_path / "plugins" / "workflow-pack" / ".codex-plugin" / "plugin.json").exists()
    assert (tmp_path / "GEMINI.md").exists()
    assert not (tmp_path / "AGENTS.md").exists()
