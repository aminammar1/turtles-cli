import json

from turtles_cli.scaffold import create_plugin, create_skill, create_subagent


def test_create_skill_uses_claude_skill_structure(tmp_path) -> None:
    result = create_skill(tmp_path, "Security Audit", "Audit secrets and risky code")

    assert result.path == tmp_path / ".claude" / "skills" / "security-audit" / "SKILL.md"
    assert "description: Audit secrets" in result.path.read_text(encoding="utf-8")


def test_create_subagent_uses_claude_agent_structure(tmp_path) -> None:
    result = create_subagent(tmp_path, "Code Reviewer", "Review diffs")

    assert result.path == tmp_path / ".claude" / "agents" / "code-reviewer.md"
    assert "tools:" in result.path.read_text(encoding="utf-8")


def test_create_plugin_uses_plugin_manifest_structure(tmp_path) -> None:
    result = create_plugin(tmp_path, "Workflow Pack", "Reusable workflow helpers")
    manifest = json.loads(result.path.read_text(encoding="utf-8"))

    assert result.path == tmp_path / "plugins" / "workflow-pack" / ".claude-plugin" / "plugin.json"
    assert manifest["name"] == "workflow-pack"
    assert (tmp_path / "plugins" / "workflow-pack" / "skills" / "review" / "SKILL.md").exists()
