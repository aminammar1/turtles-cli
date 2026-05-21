from __future__ import annotations

from pathlib import Path
from typing import Any

import typer
import uvicorn
from fastapi import FastAPI
from pydantic import BaseModel

from .audits import ai_detect, code_review, docker_audit, security_audit
from .config import load_config, redacted_config
from .prompts import evaluate_prompt, simulation_grade


api = FastAPI(title="Turtles CLI Local Server", version="0.1.0")


class PromptRequest(BaseModel):
    prompt: str
    code_involved: bool = False


def root_path() -> Path:
    return Path.cwd().resolve()


def findings_payload(findings: list[Any]) -> list[dict[str, Any]]:
    return [finding.__dict__ for finding in findings]


@api.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "scope": "project"}


@api.get("/config")
def config() -> dict[str, Any]:
    return redacted_config(load_config(root_path()))


@api.get("/review")
def review() -> dict[str, Any]:
    return {"findings": findings_payload(code_review(root_path()))}


@api.get("/security")
def security() -> dict[str, Any]:
    return {"findings": findings_payload(security_audit(root_path()))}


@api.get("/docker")
def docker() -> dict[str, Any]:
    return {"findings": findings_payload(docker_audit(root_path()))}


@api.get("/ai-detect")
def ai_detection() -> dict[str, Any]:
    estimate, findings = ai_detect(root_path())
    return {"estimate": estimate, "findings": findings_payload(findings)}


@api.post("/prompt-eval")
def prompt_eval(request: PromptRequest) -> dict[str, Any]:
    score, notes = evaluate_prompt(request.prompt)
    return {"score": score.__dict__ | {"total": score.total}, "notes": notes}


@api.post("/simulation")
def simulation(request: PromptRequest) -> dict[str, Any]:
    return simulation_grade(request.prompt, request.code_involved)


@api.get("/mcp/tools")
def mcp_tools() -> dict[str, Any]:
    return {
        "tools": [
            {"name": "code_review", "description": "Run project-level code review heuristics."},
            {"name": "security_audit", "description": "Scan for secrets and risky code patterns."},
            {"name": "docker_audit", "description": "Inspect Dockerfile and Compose files."},
            {"name": "prompt_eval", "description": "Evaluate prompt quality."},
        ]
    }


def run(
    host: str = "127.0.0.1",
    port: int = 8765,
) -> None:
    uvicorn.run("turtles_cli.server:api", host=host, port=port, reload=False)


def cli() -> None:
    typer.run(run)


if __name__ == "__main__":
    cli()
