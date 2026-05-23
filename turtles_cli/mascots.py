from __future__ import annotations

from dataclasses import dataclass

from .modes import TurtleMode


FRAME_WIDTH = 48


@dataclass(frozen=True)
class MascotSpec:
    short: str
    knot: str
    eyes: tuple[str, str]
    work_eyes: tuple[str, str]
    battle_eyes: tuple[str, str]
    smile: str


MASCOTS: dict[str, MascotSpec] = {
    "leonardo": MascotSpec("LEO", "left", ("◕", "◕"), ("◈", "◉"), ("★", "★"), "╲__________╱"),
    "donatello": MascotSpec("DON", "both", ("⊙", "⊙"), ("⊛", "⊙"), ("⊛", "⊛"), "╲__________╱"),
    "raphael": MascotSpec("RPH", "right", ("◣", "◢"), ("★", "◢"), ("★", "★"), "╲____▰▰____╱"),
    "michelangelo": MascotSpec("MIK", "left-high", ("◡", "◡"), ("⊙", "◡"), ("★", "★"), "╲_____▽____╱"),
}


def _fit(line: str) -> str:
    return line[:FRAME_WIDTH].ljust(FRAME_WIDTH)


def _eyes(spec: MascotSpec, activity: str, frame: int) -> tuple[str, str]:
    if activity == "battle":
        return spec.battle_eyes
    if activity == "work":
        left, right = spec.work_eyes
        return (right, left) if frame % 3 == 1 else (left, right)
    return spec.eyes


def _left_tail(spec: MascotSpec, frame: int) -> list[str]:
    if spec.knot not in {"left", "left-high", "both"}:
        return ["      ", "      ", "      "]
    high = spec.knot == "left-high"
    top = "  ◢◣  " if high else " ◁◁   "
    mid = " ◢██◣ " if high else "◁██◣  "
    low = "  ╰◥◤ " if frame % 2 else "  ╰◣◢ "
    return [top, mid, low]


def _right_tail(spec: MascotSpec, frame: int) -> list[str]:
    if spec.knot not in {"right", "both"}:
        return ["      ", "      ", "      "]
    top = "   ▷▷ "
    mid = " ◢██▷"
    low = " ◥◤╯ " if frame % 2 else " ◣◢╯ "
    return [top, mid, low]


def _mouth(spec: MascotSpec, activity: str, frame: int) -> tuple[str, str]:
    if activity == "battle":
        return ("╲____▰▰____╱", "     ╲_▴_╱")
    if activity == "work":
        tongue = "     ╲_⌄_╱" if frame % 2 else "      ╲_╱"
        return ("╲__________╱", tongue)
    tongue = "     ╲_▽_╱" if frame % 2 else "      ╲_╱"
    return (spec.smile, tongue)


def _frame(spec: MascotSpec, activity: str, frame: int) -> str:
    activity = activity if activity in {"idle", "work", "battle"} else "idle"
    left_eye, right_eye = _eyes(spec, activity, frame)
    smile, tongue = _mouth(spec, activity, frame)
    left_tail = _left_tail(spec, frame)
    right_tail = _right_tail(spec, frame)
    lean = " " if activity == "battle" and frame % 2 else ""

    lines = [
        f"{lean}              .-''''''''''''''-.",
        f"{lean}          .-'    green shell      '-.",
        f"{lean}       .-'    .--------------.       '-.",
        f"{lean}{left_tail[0]}   .-'   .'              '.   '-.   {right_tail[0]}",
        f"{lean}{left_tail[1]}  /   .-╯  {spec.short} BANDANA  ╰-.   \\  {right_tail[1]}",
        f"{lean}{left_tail[2]} /   /   ({left_eye})          ({right_eye})   \\   \\ {right_tail[2]}",
        f"{lean}       |   |        .----.        |   |",
        f"{lean}       |   '.___.-'      '-.___.'   |",
        f"{lean}        \\                              /",
        f"{lean}     .---\\            nose            /---.",
        f"{lean}   .'     '-.                    .-'     '.",
        f"{lean}  /           {smile:^16}           \\",
        f"{lean} /        .-.                  .-.        \\",
        f"{lean} \\          '-.______________.-'          /",
        f"{lean}  '-.              {tongue:^10}        .-'",
        f"{lean}     '-.____________________________.-'",
    ]
    return "\n".join(_fit(line) for line in lines)


def frame_count(activity: str) -> int:
    return 3 if activity == "work" else 2


def mascot_frame(mode: TurtleMode, frame: int = 0, activity: str = "idle") -> str:
    spec = MASCOTS.get(mode.key, MASCOTS["leonardo"])
    return _frame(spec, activity, frame % frame_count(activity))
