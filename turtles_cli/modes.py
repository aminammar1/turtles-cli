from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class TurtleMode:
    key: str
    name: str
    color: str
    personality: str
    focus: str


MODES: dict[str, TurtleMode] = {
    "leonardo": TurtleMode(
        key="leonardo",
        name="Leonardo",
        color="blue",
        personality="Balanced and strategic",
        focus="Structured thinking, full planning mode.",
    ),
    "donatello": TurtleMode(
        key="donatello",
        name="Donatello",
        color="purple",
        personality="Technical and deep",
        focus="Advanced analysis, architecture-focused.",
    ),
    "raphael": TurtleMode(
        key="raphael",
        name="Raphael",
        color="red",
        personality="Fast and aggressive",
        focus="Quick audits, blunt feedback, speed mode.",
    ),
    "michelangelo": TurtleMode(
        key="michelangelo",
        name="Michelangelo",
        color="orange1",
        personality="Creative and fun",
        focus="Experimental prompts, creative suggestions.",
    ),
}

DEFAULT_MODE = MODES["leonardo"]


def get_mode(name: str | None) -> TurtleMode:
    if not name:
        return DEFAULT_MODE
    normalized = name.strip().lower()
    return MODES.get(normalized, DEFAULT_MODE)
