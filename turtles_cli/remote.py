"""Remote machine connection manager for turtle-mode.

Handles SSH connections to remote machines (EC2 instances, etc.) and local
machine command execution. Provides agent detection, ping checks, and
streamed command execution for code assistant CLIs.
"""

from __future__ import annotations

import os
import subprocess
import threading
import time
from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path

try:
    import paramiko
except ImportError:  # pragma: no cover – graceful fallback
    paramiko = None  # type: ignore[assignment]


# ---------------------------------------------------------------------------
# Known code assistant CLI agents and their one-shot invocation patterns
# ---------------------------------------------------------------------------

KNOWN_AGENTS: dict[str, dict[str, str]] = {
    "gemini": {
        "binary": "gemini",
        "label": "Gemini CLI",
        "invoke": 'gemini -p "{prompt}"',
    },
    "claude": {
        "binary": "claude",
        "label": "Claude Code",
        "invoke": 'claude -p "{prompt}"',
    },
    "agy": {
        "binary": "agy",
        "label": "Antigravity SDK",
        "invoke": 'agy --prompt "{prompt}" --dangerously-skip-permissions',
    },
    "codex": {
        "binary": "codex",
        "label": "Codex CLI",
        "invoke": 'codex "{prompt}"',
    },
    "opencode": {
        "binary": "opencode",
        "label": "OpenCode",
        "invoke": 'opencode run "{prompt}"',
    },
}


# ---------------------------------------------------------------------------
# Machine dataclasses
# ---------------------------------------------------------------------------


@dataclass
class RemoteMachine:
    """An SSH-reachable machine."""

    name: str
    host: str
    user: str
    key_path: str = ""
    port: int = 22
    project_path: str = ""


@dataclass
class LocalMachine:
    """The machine running Turtles CLI."""

    name: str = "local"
    project_path: str = ""


@dataclass
class MachineConnection:
    """A live (or failed) connection to a machine."""

    machine: RemoteMachine | LocalMachine
    ssh_client: object | None = None  # paramiko.SSHClient or None for local
    status: str = "disconnected"  # connected | failed | disconnected
    error: str = ""
    detected_agents: list[str] = field(default_factory=list)

    @property
    def is_local(self) -> bool:
        return isinstance(self.machine, LocalMachine)

    @property
    def label(self) -> str:
        if self.is_local:
            return f"🖥  {self.machine.name}"
        machine = self.machine
        assert isinstance(machine, RemoteMachine)
        return f"🌐 {machine.name} ({machine.user}@{machine.host}:{machine.port})"


# ---------------------------------------------------------------------------
# Connection helpers
# ---------------------------------------------------------------------------


def _require_paramiko() -> None:
    if paramiko is None:
        raise RuntimeError(
            "paramiko is required for remote SSH connections. "
            "Install it with: uv add paramiko"
        )


def connect_local(root: Path) -> MachineConnection:
    """Create a connection handle for the local machine."""
    machine = LocalMachine(project_path=str(root))
    return MachineConnection(machine=machine, status="connected")


def connect_remote(machine: RemoteMachine) -> MachineConnection:
    """Open an SSH session to a remote machine."""
    _require_paramiko()
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    try:
        connect_kwargs: dict[str, object] = {
            "hostname": machine.host,
            "port": machine.port,
            "username": machine.user,
            "timeout": 15,
        }
        key_path = os.path.expanduser(machine.key_path) if machine.key_path else ""
        if key_path and os.path.isfile(key_path):
            connect_kwargs["key_filename"] = key_path
        else:
            # Fall back to SSH agent / default keys
            connect_kwargs["allow_agent"] = True
            connect_kwargs["look_for_keys"] = True

        client.connect(**connect_kwargs)  # type: ignore[arg-type]
        return MachineConnection(machine=machine, ssh_client=client, status="connected")
    except Exception as exc:  # noqa: BLE001
        return MachineConnection(machine=machine, status="failed", error=str(exc))


def disconnect(conn: MachineConnection) -> None:
    """Close the SSH session if open."""
    if conn.ssh_client is not None and hasattr(conn.ssh_client, "close"):
        try:
            conn.ssh_client.close()
        except Exception:  # noqa: BLE001
            pass
    conn.status = "disconnected"


# ---------------------------------------------------------------------------
# Command execution
# ---------------------------------------------------------------------------


def run_command(conn: MachineConnection, cmd: str, *, timeout: float = 30) -> tuple[int, str, str]:
    """Run *cmd* on the connected machine.

    Returns ``(exit_code, stdout, stderr)``.
    """
    if conn.is_local:
        return _run_local(cmd, cwd=conn.machine.project_path or None, timeout=timeout)
    return _run_remote(conn, cmd, timeout=timeout)


def _run_local(cmd: str, *, cwd: str | None = None, timeout: float = 30) -> tuple[int, str, str]:
    try:
        result = subprocess.run(
            ["bash", "-lc", cmd],
            cwd=cwd,
            text=True,
            capture_output=True,
            check=False,
            timeout=timeout,
        )
        return result.returncode, result.stdout, result.stderr
    except subprocess.TimeoutExpired:
        return 1, "", f"Command timed out after {timeout}s"
    except OSError as exc:
        return 1, "", str(exc)


def _run_remote(conn: MachineConnection, cmd: str, *, timeout: float = 30) -> tuple[int, str, str]:
    _require_paramiko()
    if conn.ssh_client is None:
        return 1, "", "SSH client is not connected."
    try:
        # Wrap in bash -lc to load full shell environment/PATH
        safe_cmd = cmd.replace("'", "'\\''")
        login_cmd = f"bash -lc '{safe_cmd}'"
        _stdin, _stdout, _stderr = conn.ssh_client.exec_command(login_cmd, timeout=timeout)  # type: ignore[union-attr]
        stdout = _stdout.read().decode("utf-8", errors="replace")
        stderr = _stderr.read().decode("utf-8", errors="replace")
        exit_code = _stdout.channel.recv_exit_status()
        return exit_code, stdout, stderr
    except Exception as exc:  # noqa: BLE001
        return 1, "", f"Remote exec failed: {exc}"


# ---------------------------------------------------------------------------
# Ping / connectivity check
# ---------------------------------------------------------------------------


def ping(conn: MachineConnection) -> bool:
    """Quick connectivity check — runs ``echo ok`` on the machine."""
    if conn.status != "connected":
        return False
    code, stdout, _ = run_command(conn, "echo ok", timeout=10)
    return code == 0 and "ok" in stdout


# ---------------------------------------------------------------------------
# Agent detection
# ---------------------------------------------------------------------------


def detect_agents(conn: MachineConnection) -> list[str]:
    """Detect which code assistant CLIs are installed on the machine."""
    found: list[str] = []
    for key, info in KNOWN_AGENTS.items():
        binary = info["binary"]
        code, stdout, _ = run_command(conn, f"which {binary} 2>/dev/null", timeout=10)
        if code == 0 and stdout.strip():
            found.append(key)
    conn.detected_agents = found
    return found


# ---------------------------------------------------------------------------
# Streamed agent execution
# ---------------------------------------------------------------------------


def _build_agent_command(agent_key: str, prompt: str, project_path: str) -> str:
    """Build the shell command to invoke an agent with a prompt."""
    info = KNOWN_AGENTS.get(agent_key)
    if info is None:
        raise ValueError(f"Unknown agent: {agent_key}")
    # Escape single quotes in the prompt for safe shell embedding
    safe_prompt = prompt.replace("'", "'\\''")
    # Use the project_path as cwd via cd
    invoke = info["invoke"].replace("{prompt}", safe_prompt)
    if project_path:
        return f"cd {project_path} && {invoke}"
    return invoke


def stream_agent_local(
    agent_key: str, prompt: str, project_path: str, *, timeout: float = 120
) -> Iterator[str]:
    """Run an agent locally and yield output lines as they arrive."""
    cmd = _build_agent_command(agent_key, prompt, project_path)
    try:
        proc = subprocess.Popen(
            ["bash", "-lc", cmd],
            cwd=project_path or None,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )
        assert proc.stdout is not None
        start = time.monotonic()
        for line in proc.stdout:
            yield line
            if time.monotonic() - start > timeout:
                proc.kill()
                yield "\n[timeout reached]\n"
                break
        proc.wait(timeout=5)
    except Exception as exc:  # noqa: BLE001
        yield f"\n[error: {exc}]\n"


def stream_agent_remote(
    conn: MachineConnection,
    agent_key: str,
    prompt: str,
    project_path: str,
    *,
    timeout: float = 120,
) -> Iterator[str]:
    """Run an agent over SSH and yield output lines as they arrive."""
    _require_paramiko()
    if conn.ssh_client is None:
        yield "[error: SSH client not connected]\n"
        return
    cmd = _build_agent_command(agent_key, prompt, project_path)
    try:
        # Wrap in bash -lc to load full shell environment/PATH
        safe_cmd = cmd.replace("'", "'\\''")
        login_cmd = f"bash -lc '{safe_cmd}'"
        _stdin, _stdout, _stderr = conn.ssh_client.exec_command(login_cmd, timeout=timeout, get_pty=True)  # type: ignore[union-attr]
        start = time.monotonic()
        for line in _stdout:
            if isinstance(line, bytes):
                line = line.decode("utf-8", errors="replace")
            yield line
            if time.monotonic() - start > timeout:
                yield "\n[timeout reached]\n"
                break
    except Exception as exc:  # noqa: BLE001
        yield f"\n[error: {exc}]\n"


def collect_agent_output(
    conn: MachineConnection,
    agent_key: str,
    prompt: str,
    project_path: str,
    *,
    output_lines: list[str],
    timeout: float = 120,
) -> None:
    """Threaded helper: stream agent output into *output_lines* list.

    Designed to be run via ``threading.Thread(target=collect_agent_output, ...)``.
    """
    if conn.is_local:
        gen = stream_agent_local(agent_key, prompt, project_path, timeout=timeout)
    else:
        gen = stream_agent_remote(conn, agent_key, prompt, project_path, timeout=timeout)
    for line in gen:
        output_lines.append(line)


# ---------------------------------------------------------------------------
# Machine config serialization helpers
# ---------------------------------------------------------------------------


def machine_from_dict(data: dict[str, object]) -> RemoteMachine:
    """Deserialize a remote machine from config dict."""
    return RemoteMachine(
        name=str(data.get("name", "remote")),
        host=str(data.get("host", "")),
        user=str(data.get("user", "ubuntu")),
        key_path=str(data.get("key_path", "")),
        port=int(data.get("port", 22)),  # type: ignore[arg-type]
        project_path=str(data.get("project_path", "")),
    )


def machine_to_dict(machine: RemoteMachine) -> dict[str, object]:
    """Serialize a remote machine for config storage."""
    return {
        "name": machine.name,
        "host": machine.host,
        "user": machine.user,
        "key_path": machine.key_path,
        "port": machine.port,
        "project_path": machine.project_path,
    }
