"""Turtle-mode: multi-agent orchestration across machines.

Connects to local + remote machines, detects installed code-assistant CLIs,
sends the same prompt to two agents simultaneously, streams both responses,
and asks the configured AI to grade how they collaborated.
"""

from __future__ import annotations

import threading
import time
from pathlib import Path

from rich import box

from rich.live import Live
from rich.panel import Panel
from rich.prompt import Confirm, Prompt
from rich.table import Table
from rich.text import Text
from rich.markdown import Markdown

from .config import TurtlesConfig, save_config
from .llm import LLMError, complete_text, provider_ready
from .modes import TurtleMode, get_mode
from .prompting import ask_project_text, choose_from_keyboard
from .remote import (
    KNOWN_AGENTS,
    MachineConnection,
    RemoteMachine,
    collect_agent_output,
    connect_local,
    connect_remote,
    detect_agents,
    disconnect,
    machine_from_dict,
    machine_to_dict,
    ping,
)
from .ui import (
    UNICODE_OK,
    command_pick_animation,
    console,
    divider,
    markdown_panel,
    panel,
    processing_animation,
    shell_problem,
    status,
)


# ---------------------------------------------------------------------------
# Phase animations — themed to match existing UI
# ---------------------------------------------------------------------------

_SPINNER = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"] if UNICODE_OK else ["-", "\\", "|", "/"]


def _turtle_mode_intro_animation(mode: TurtleMode, *, enabled: bool = True) -> None:
    """Themed startup animation for turtle-mode."""
    if not enabled or not console.is_terminal:
        return
    frames = [
        f"[bold {mode.color}]opening sewer channels[/bold {mode.color}]",
        f"[bold {mode.color}]establishing remote links[/bold {mode.color}]",
        f"[bold {mode.color}]detecting agents[/bold {mode.color}]",
        f"[bold {mode.color}]syncing shells[/bold {mode.color}]",
        f"[bold {mode.color}]turtle-mode ready[/bold {mode.color}]",
    ]
    with Live("", console=console, refresh_per_second=12, transient=True) as live:
        for frame in frames:
            body = Table.grid(expand=False)
            body.add_column()
            body.add_row(Text.from_markup(f"> {frame}"))
            live.update(body)
            time.sleep(0.15)


def _phase_animation(label: str, mode: TurtleMode) -> None:
    """Quick 3-frame animation between phases — mirrors command_pick_animation."""
    if not console.is_terminal:
        return
    frames = [
        f"[bold {mode.color}]mask on[/bold {mode.color}]  {label}",
        f"[bold {mode.color}]shadow step[/bold {mode.color}]  {label}",
        f"[bold {mode.color}]shell strike[/bold {mode.color}]  {label}",
    ]
    with Live("", console=console, refresh_per_second=12, transient=True) as live:
        for frame in frames:
            live.update(Text.from_markup(f"> {frame}"))
            time.sleep(0.08)


def _render_markdown_slice(text: str, max_lines: int) -> Text | str:
    """Render full markdown to console and return the last `max_lines` lines as a Text object."""
    if not text.strip():
        return ""
    # Approximate width for the panel content
    width = (console.width // 2) - 4 if console.width else 40
    if width < 20:
        width = 20
    from rich.console import Console
    # Create a lightweight console with the specific width
    temp_console = Console(width=width, force_terminal=True, color_system="truecolor")
    try:
        with temp_console.capture() as capture:
            temp_console.print(Markdown(text))
        rendered = capture.get()
        lines = rendered.splitlines()
        sliced = lines[-max_lines:] if len(lines) > max_lines else lines
        return Text.from_ansi("\n".join(sliced))
    except Exception:
        # Fallback to plain text slice if anything fails
        lines = text.splitlines()
        sliced = lines[-max_lines:] if len(lines) > max_lines else lines
        return "\n".join(sliced)


# ---------------------------------------------------------------------------
# Phase 1 — Connection setup
# ---------------------------------------------------------------------------


def _configure_machines(root: Path, config: TurtlesConfig) -> list[RemoteMachine]:
    """Let the user add / reuse remote machine configurations."""
    saved = config.remote_machines
    machines: list[RemoteMachine] = [machine_from_dict(entry) for entry in saved]

    if machines:
        summary = "\n".join(f"  {m.name}: {m.user}@{m.host}:{m.port} ({m.project_path})" for m in machines)
        console.print(f"[dim]Saved remote machines:[/dim]\n{summary}")
        if Confirm.ask("Use saved machines?", default=True):
            return machines
        machines.clear()

    console.print("[dim]Configure at least one remote machine (EC2 instance, etc.).[/dim]")
    while True:
        name = Prompt.ask("Machine name", default=f"ec2-agent-{len(machines) + 1}")
        host = Prompt.ask("Host (IP or hostname)")
        user = Prompt.ask("SSH user", default="ubuntu")
        key_path = Prompt.ask("SSH key path (leave blank for agent/default)", default="")
        port = int(Prompt.ask("SSH port", default="22"))
        project_path = Prompt.ask("Remote project path", default=str(root))

        machines.append(
            RemoteMachine(
                name=name,
                host=host,
                user=user,
                key_path=key_path,
                port=port,
                project_path=project_path,
            )
        )
        if not Confirm.ask("Add another remote machine?", default=False):
            break

    # Persist the configuration
    config.remote_machines = [machine_to_dict(m) for m in machines]
    save_config(config, root)
    return machines


def _phase_connect(
    root: Path, config: TurtlesConfig, mode: TurtleMode
) -> list[MachineConnection]:
    """Phase 1: establish connections to local + remote machines."""
    _phase_animation("Phase 1: establishing connections", mode)

    remote_machines = _configure_machines(root, config)
    connections: list[MachineConnection] = []

    # Local machine
    local_conn = connect_local(root)
    connections.append(local_conn)

    # Remote machines
    for machine in remote_machines:
        with processing_animation(
            f"Connecting to {machine.name}",
            mode,
            phases=["resolving host", "authenticating SSH", "opening channel", "verifying"],
        ):
            conn = connect_remote(machine)
        connections.append(conn)

    # Display connection status
    table = Table(
        title="Machine Connections",
        box=box.ROUNDED,
        header_style=f"bold {mode.color}",
    )
    table.add_column("Machine")
    table.add_column("Status")
    table.add_column("Ping")
    table.add_column("Details")

    for conn in connections:
        ping_ok = ping(conn)
        ping_str = "[green]✓ ok[/green]" if ping_ok else "[red]✗ fail[/red]"
        if conn.status == "connected":
            status_str = "[green]connected[/green]"
        elif conn.status == "failed":
            status_str = "[red]failed[/red]"
        else:
            status_str = "[yellow]disconnected[/yellow]"
        details = conn.error or ("local subprocess" if conn.is_local else "SSH")
        table.add_row(conn.label, status_str, ping_str, details)

    console.print(table)

    # Filter out failed connections
    active = [c for c in connections if c.status == "connected"]
    if len(active) < 2:
        shell_problem(
            f"Need at least 2 connected machines for turtle-mode. Got {len(active)}. "
            "Check SSH keys, host addresses, and security groups."
        )
        for conn in connections:
            disconnect(conn)
        return []

    return active


# ---------------------------------------------------------------------------
# Phase 2 — Agent detection
# ---------------------------------------------------------------------------


def _phase_detect(
    connections: list[MachineConnection], mode: TurtleMode
) -> dict[str, str]:
    """Phase 2: detect code assistants on each machine.

    Returns a mapping of ``connection_label -> chosen_agent_key``.
    """
    _phase_animation("Phase 2: scanning for agents", mode)

    for conn in connections:
        with processing_animation(
            f"Detecting agents on {conn.label}",
            mode,
            phases=["checking gemini", "checking claude", "checking agy", "checking codex", "checking opencode"],
        ):
            detect_agents(conn)

    # Display detection table
    table = Table(
        title="Agent Detection",
        box=box.ROUNDED,
        header_style=f"bold {mode.color}",
    )
    table.add_column("Machine")
    for key, info in KNOWN_AGENTS.items():
        table.add_column(info["label"])

    for conn in connections:
        row = [conn.label]
        for key in KNOWN_AGENTS:
            if key in conn.detected_agents:
                row.append("[green]✓[/green]")
            else:
                row.append("[dim]—[/dim]")
        table.add_row(*row)

    console.print(table)

    # Let user pick agent per machine
    assignments: dict[str, str] = {}
    for conn in connections:
        if not conn.detected_agents:
            shell_problem(f"No code assistant found on {conn.label}. Skipping.")
            continue

        agent_labels = [
            f"{KNOWN_AGENTS[key]['label']} ({key})" for key in conn.detected_agents
        ]
        picked = choose_from_keyboard(
            f"Agent for {conn.label}",
            agent_labels,
            default=agent_labels[0],
        )
        # Extract key from "Label (key)" format
        agent_key = picked.split("(")[-1].rstrip(")")
        assignments[conn.label] = agent_key

    if len(assignments) < 2:
        shell_problem("Need agents on at least 2 machines. Install a code assistant CLI on missing machines.")
        return {}

    return assignments


# ---------------------------------------------------------------------------
# Phase 3 — Dual prompt execution with streamed output
# ---------------------------------------------------------------------------


def _phase_execute(
    connections: list[MachineConnection],
    assignments: dict[str, str],
    mode: TurtleMode,
    root: Path,
) -> tuple[str, list[tuple[str, str, str]]]:
    """Phase 3: send one prompt to two agents, stream responses.

    Returns ``(prompt, [(machine_label, agent_key, response_text), ...])``.
    """
    _phase_animation("Phase 3: deploying turtle formation", mode)

    prompt = ask_project_text(root, "Prompt for both agents")
    if not prompt.strip():
        shell_problem("Empty prompt. Aborting.")
        return "", []

    console.print(f"\n[bold {mode.color}]Sending prompt to {len(assignments)} agents...[/bold {mode.color}]")
    divider()

    # Prepare threaded execution
    outputs: dict[str, list[str]] = {}
    threads: list[threading.Thread] = []

    active_conns = {conn.label: conn for conn in connections if conn.label in assignments}

    for label, agent_key in assignments.items():
        conn = active_conns.get(label)
        if conn is None:
            continue
        project_path = conn.machine.project_path
        output_lines: list[str] = []
        outputs[label] = output_lines

        thread = threading.Thread(
            target=collect_agent_output,
            args=(conn, agent_key, prompt, project_path),
            kwargs={"output_lines": output_lines, "timeout": 300},
            daemon=True,
        )
        threads.append(thread)

    # Start all threads
    for thread in threads:
        thread.start()

    # Live render both streams side by side
    started = time.monotonic()
    labels = list(assignments.keys())

    with Live("", console=console, refresh_per_second=6, transient=False) as live:
        while any(t.is_alive() for t in threads):
            elapsed = time.monotonic() - started
            frame_idx = int(elapsed * 6) % len(_SPINNER)
            spinner = _SPINNER[frame_idx]

            panels = []
            for label in labels:
                agent_key = assignments[label]
                agent_label = KNOWN_AGENTS.get(agent_key, {}).get("label", agent_key)
                lines = outputs.get(label, [])
                if lines:
                    full_text = "".join(lines)
                    visible = _render_markdown_slice(full_text, 25)
                else:
                    visible = f"{spinner} waiting for response..."
                title = f"{agent_label} on {label}"
                border = mode.color
                panels.append(
                    Panel(
                        visible,
                        title=f"[bold {border}]{title}[/bold {border}]",
                        border_style=border,
                        box=box.ROUNDED,
                        expand=True,
                    )
                )

            layout = Table.grid(expand=True)
            for _ in panels:
                layout.add_column(ratio=1)
            layout.add_row(*panels)

            status_line = Text(f"  {spinner} streaming responses... elapsed {elapsed:.1f}s", style=f"bold {mode.color}")
            outer = Table.grid(expand=True)
            outer.add_column()
            outer.add_row(layout)
            outer.add_row(status_line)
            live.update(outer)
            time.sleep(0.16)

        # Final state
        elapsed = time.monotonic() - started
        final_panels = []
        for label in labels:
            agent_key = assignments[label]
            agent_label = KNOWN_AGENTS.get(agent_key, {}).get("label", agent_key)
            lines = outputs.get(label, [])
            if lines:
                full_text = "".join(lines)
                visible = _render_markdown_slice(full_text, 40)
            else:
                visible = "[dim]No output received.[/dim]"
            title = f"{agent_label} on {label}"
            final_panels.append(
                Panel(
                    visible,
                    title=f"[bold {mode.color}]{title}[/bold {mode.color}]",
                    border_style=mode.color,
                    box=box.ROUNDED,
                    expand=True,
                )
            )
        final_layout = Table.grid(expand=True)
        for _ in final_panels:
            final_layout.add_column(ratio=1)
        final_layout.add_row(*final_panels)
        done_line = Text(f"  ✓ Both agents completed in {elapsed:.1f}s", style=f"bold {mode.color}")
        final_outer = Table.grid(expand=True)
        final_outer.add_column()
        final_outer.add_row(final_layout)
        final_outer.add_row(done_line)
        live.update(final_outer)

    # Collect full results
    results: list[tuple[str, str, str]] = []
    for label in labels:
        agent_key = assignments[label]
        lines = outputs.get(label, [])
        full_text = "".join(lines)
        results.append((label, agent_key, full_text))

    return prompt, results


# ---------------------------------------------------------------------------
# Phase 4 — AI grading
# ---------------------------------------------------------------------------


def _phase_grade(
    prompt: str,
    results: list[tuple[str, str, str]],
    config: TurtlesConfig,
    mode: TurtleMode,
    root: Path,
) -> None:
    """Phase 4: AI grades the collaboration between agents."""
    _phase_animation("Phase 4: master splinter evaluating", mode)

    if not provider_ready(config):
        shell_problem("No AI provider configured. Run /login to enable grading.")
        # Still show raw results
        for label, agent_key, text in results:
            agent_label = KNOWN_AGENTS.get(agent_key, {}).get("label", agent_key)
            panel(f"{agent_label} on {label}", text[:3000] or "[no output]", mode)
        return

    # Build grading prompt
    agent_sections = []
    for idx, (label, agent_key, text) in enumerate(results, 1):
        agent_label = KNOWN_AGENTS.get(agent_key, {}).get("label", agent_key)
        truncated = text[:6000] if len(text) > 6000 else text
        agent_sections.append(
            f"--- Agent {idx}: {agent_label} on {label} ---\n{truncated or '[no output]'}"
        )

    sections_text = "\n\n".join(agent_sections)
    grading_prompt = (
        f"Two AI code assistants were given the SAME prompt on the SAME project simultaneously.\n\n"
        f"Prompt given:\n{prompt}\n\n"
        f"{sections_text}\n\n"
        "Analyze and grade their work:\n"
        "1. **Individual Quality**: Rate each agent's response (A-F) for correctness, completeness, and clarity.\n"
        "2. **Coherence**: Would their outputs conflict if both were applied? Identify overlaps or contradictions.\n"
        "3. **Complementarity**: Do they cover different aspects? Could they complement each other?\n"
        "4. **Collaboration Score**: Overall grade (A-F) on how well multi-agent work would function on this project.\n"
        "5. **Recommendation**: Should multiple agents work on this project simultaneously? What risks exist?\n\n"
        "Be concise and specific. Reference actual content from their responses."
    )

    system = (
        "You are an expert evaluator for multi-agent coding collaboration. "
        "You are grading how two independent AI code assistants performed on the same task. "
        "Focus on practical implications of running multiple agents on one project."
    )

    try:
        with processing_animation(
            "Master Splinter grading agent collaboration",
            mode,
            phases=["reading agent 1 output", "reading agent 2 output", "comparing approaches", "scoring collaboration", "writing report"],
        ):
            response = complete_text(config, system, grading_prompt, timeout=60.0)
        markdown_panel("🏆 Turtle Mode — Collaboration Report", response.text, mode)
        status(f"Graded with {response.provider} / {response.model}.", mode, style="green")
    except LLMError as exc:
        shell_problem(f"AI grading failed: {exc}")
        # Fallback: show raw results
        for label, agent_key, text in results:
            agent_label = KNOWN_AGENTS.get(agent_key, {}).get("label", agent_key)
            panel(f"{agent_label} on {label}", text[:3000] or "[no output]", mode)


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------


def run_turtle_mode(args: list[str], root: Path, config: TurtlesConfig) -> TurtlesConfig:
    """Full turtle-mode orchestration: connect → detect → execute → grade."""
    mode = get_mode(config.mode)

    # Warning banner
    console.print(
        Panel(
            "[bold yellow]⚠  TURTLE MODE — EXPERIMENTAL[/bold yellow]\n\n"
            "[yellow]This command orchestrates multiple AI code assistants across machines.\n"
            "Both agents will work on the SAME project simultaneously.\n\n"
            "• Test with simple, non-destructive prompts first\n"
            "• Agents may produce conflicting changes\n"
            "• The goal is to observe multi-agent collaboration behavior[/yellow]",
            title="[bold yellow]Turtle Mode[/bold yellow]",
            border_style="yellow",
            box=box.HEAVY,
        )
    )

    if not Confirm.ask("[bold]Proceed with turtle-mode?[/bold]", default=True):
        console.print("[dim]Turtle mode cancelled.[/dim]")
        return config

    # Intro animation
    _turtle_mode_intro_animation(mode, enabled=config.display.show_animation)
    divider()

    # Phase 1: Connect
    connections = _phase_connect(root, config, mode)
    if not connections:
        return config
    divider()

    # Phase 2: Detect agents
    assignments = _phase_detect(connections, mode)
    if not assignments:
        for conn in connections:
            disconnect(conn)
        return config
    divider()

    # Phase 3: Execute prompts
    prompt, results = _phase_execute(connections, assignments, mode, root)
    if not results:
        for conn in connections:
            disconnect(conn)
        return config
    divider()

    # Phase 4: Grade
    _phase_grade(prompt, results, config, mode, root)
    divider()

    # Cleanup
    for conn in connections:
        disconnect(conn)
    status("Turtle mode session complete. All connections closed.", mode, style="green")

    return config
