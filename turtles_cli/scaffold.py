from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class ScaffoldResult:
    kind: str
    name: str
    path: Path


def slugify(value: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9-]+", "-", value.strip().lower()).strip("-")
    return slug or "turtle-extension"


def create_skill(root: Path, name: str, description: str, *, allowed_tools: str = "Read Grep Glob Bash") -> ScaffoldResult:
    slug = slugify(name)
    directory = root / ".claude" / "skills" / slug
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / "SKILL.md"
    path.write_text(
        f"""---
name: {slug}
description: {description}
allowed-tools: {allowed_tools}
---

# {name}

## When To Use
Use this skill when: {description}

## Workflow
1. Restate the user's goal and project scope.
2. Inspect only the files needed for the task.
3. Produce concise findings, risks, and verification steps.

## Output
- Summary
- Findings
- Recommended next action

## Notes
Keep the work project-level. Do not access machine-level, enterprise, or unrelated resources.
""",
        encoding="utf-8",
    )
    (directory / "examples").mkdir(exist_ok=True)
    (directory / "scripts").mkdir(exist_ok=True)
    return ScaffoldResult("skill", slug, path)


def create_subagent(root: Path, name: str, description: str, *, tools: str = "Read, Grep, Glob, Bash") -> ScaffoldResult:
    slug = slugify(name)
    directory = root / ".claude" / "agents"
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{slug}.md"
    path.write_text(
        f"""---
name: {slug}
description: {description}
tools: {tools}
---

# {name}

You are a focused project-level subagent for Turtles CLI.

## Mission
{description}

## Operating Rules
- Stay inside the current project folder.
- Prefer evidence from files and commands over assumptions.
- Return concise, actionable output.
- Include risks and verification steps when relevant.

## Response Shape
1. What you checked
2. Findings
3. Recommended next step
""",
        encoding="utf-8",
    )
    return ScaffoldResult("subagent", slug, path)


def create_plugin(root: Path, name: str, description: str, *, author: str = "Turtles CLI user") -> ScaffoldResult:
    slug = slugify(name)
    directory = root / "plugins" / slug
    manifest_dir = directory / ".claude-plugin"
    skill_dir = directory / "skills" / "review"
    agent_dir = directory / "agents"
    hooks_dir = directory / "hooks"
    for path in (manifest_dir, skill_dir, agent_dir, hooks_dir, directory / "bin"):
        path.mkdir(parents=True, exist_ok=True)

    manifest = {
        "name": slug,
        "description": description,
        "version": "0.1.0",
        "author": {"name": author},
        "license": "MIT",
    }
    manifest_path = manifest_dir / "plugin.json"
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    (skill_dir / "SKILL.md").write_text(
        f"""---
description: {description}
---

# {name} Review Skill

Use this plugin skill to support: {description}

Return a short summary, concrete findings, and verification steps.
""",
        encoding="utf-8",
    )
    (agent_dir / "reviewer.md").write_text(
        f"""---
name: {slug}-reviewer
description: Reviewer agent for {description}
tools: Read, Grep, Glob, Bash
---

Review the project for {description}. Stay project-scoped and provide actionable findings.
""",
        encoding="utf-8",
    )
    (hooks_dir / "hooks.json").write_text("[]\n", encoding="utf-8")
    (directory / "README.md").write_text(
        f"""# {name}

{description}

## Structure
- `.claude-plugin/plugin.json`: plugin manifest
- `skills/`: plugin skills
- `agents/`: plugin agents
- `hooks/`: hook configuration
- `bin/`: executable helpers

Test locally with a Claude-compatible plugin loader, for example:

```bash
claude --plugin-dir ./plugins/{slug}
```
""",
        encoding="utf-8",
    )
    return ScaffoldResult("plugin", slug, manifest_path)
