from __future__ import annotations

from dataclasses import dataclass

from rich.text import Text

from .modes import TurtleMode


FRAME_WIDTH = 48

# ── backward-compat: tests import MASCOTS ──────────────────────


@dataclass(frozen=True)
class MascotSpec:
    short: str


MASCOTS: dict[str, MascotSpec] = {
    "leonardo": MascotSpec("LEO"),
    "donatello": MascotSpec("DON"),
    "raphael": MascotSpec("RPH"),
    "michelangelo": MascotSpec("MIK"),
}

# ── colour palette (RGB) ───────────────────────────────────────
#
# Designed to mimic the bold pop-art TMNT poster look:
#   • heavy black outlines (K) around the head and bandana
#   • three-tone green skin shading (h highlight → G mid → g shadow → d deep)
#   • crisp eye whites with a tiny sparkle highlight
#   • yellow chest plate with amber shadow lines
#   • per-turtle weapon hints in steel / wood / brown tones
#
# Per-turtle skin tinting is applied at render time via SKIN_TINTS,
# so Raphael's skin reads darker / Michelangelo's reads more teal
# without needing four separate pixel grids.
# ───────────────────────────────────────────────────────────────

PALETTE: dict[str, tuple[int, int, int] | None] = {
    "_": None,
    # ─ skin tones (base, shifted per-turtle by SKIN_TINTS) ─
    "h": (120, 200, 110),     # highlight green (cheek / dome top)
    "G": (76, 175, 80),       # mid green (main skin)
    "g": (46, 125, 50),       # shadow green (chin / side of head)
    "d": (28, 85, 35),        # deep green (under-shell / deep shadow)
    # ─ outline / structural ─
    "K": (18, 18, 18),        # near-black outline (comic ink)
    "X": (8, 8, 8),            # pure black (pupils, deepest line)
    # ─ eyes ─
    "W": (245, 245, 245),     # eye white
    "w": (255, 255, 255),     # eye sparkle (brightest)
    # ─ mouth / teeth ─
    "M": (40, 22, 18),         # mouth interior / lip line
    "T": (250, 250, 245),     # teeth (Mike's grin)
    # ─ chest plate / shell ─
    "Y": (255, 213, 79),       # plastron yellow
    "y": (210, 165, 40),       # plastron amber shadow
    "S": (35, 100, 42),         # shell rim back
    # ─ straps / leather ─
    "b": (141, 110, 99),        # tan leather strap
    "B": (90, 55, 30),           # dark leather / buckle
    # ─ weapon tones ─
    "s": (180, 185, 195),        # steel blade / sai
    "i": (110, 115, 125),        # darker steel shading
    "u": (175, 130, 75),         # wood (bo staff, nunchaku handles)
    "U": (110, 75, 35),          # dark wood shadow
    "c": (40, 40, 40),           # nunchaku chain
    # ─ misc face detail ─
    "n": (42, 105, 48),          # nostril dots
}

BANDANA_COLORS: dict[str, tuple[int, int, int]] = {
    "leonardo": (33, 150, 243),      # blue
    "donatello": (156, 39, 176),     # purple
    "raphael": (229, 57, 53),        # red
    "michelangelo": (255, 152, 0),   # orange
}

# ── per-turtle skin tint (added to the four green-skin tones) ──
# Raphael is brawnier and darker; Mike's skin reads more teal.
SKIN_TINTS: dict[str, tuple[int, int, int]] = {
    "leonardo":    (  0,   0,   0),
    "donatello":   ( -4,  -2,  -2),  # very slight olive shift
    "raphael":     (-12, -18, -14),  # noticeably darker
    "michelangelo":( -8,  +6, +18),  # lighter, teal-shifted
}

_SKIN_KEYS = frozenset({"h", "G", "g", "d"})

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  Pixel grids  –  32 cols × 32 rows
#
#  Layout (16 terminal rows after half-block packing):
#    rows  0– 5  : head dome (outlined)
#    rows  6– 7  : top bandana band + knot/tails (per-turtle)
#    rows  8–11  : eyes region (brow + eye whites + pupil + sparkle)
#    rows 12–13  : bandana bottom band
#    rows 14–15  : cheeks + nose nostrils
#    rows 16–17  : mouth (per-turtle)
#    rows 18–19  : chin / jaw
#    rows 20–25  : neck + shoulders + shell rim
#    rows 26–31  : chest plate + weapon hints
#
#  Special chars per row may carry weapon glyphs that overlap
#  shoulders; they're drawn on top of the body grid via the
#  per-turtle _WEAPON_OVERLAY mapping.
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

# ── shared head silhouette (rows 0-5, dome) ────────────────────
_DOME = [
    "____________KKKKKKKK____________",  # 0
    "_________KKKGGGGGGGGKKK_________",  # 1
    "_______KKGGGGGGGGGGGGGGKK_______",  # 2
    "______KGGGhhGGGGGGGGhhGGGK______",  # 3  cheekbone/temple highlights
    "_____KGGGGGGGGGGGGGGGGGGGGK_____",  # 4
    "____KGGGGGGGGGGGGGGGGGGGGGGK____",  # 5
]

# ── shared face lower region (rows 14-19) ──────────────────────
_FACE_LOWER = [
    "____KGGGGGGGGGGGGGGGGGGGGGGK____",  # 14  upper cheeks
    "____KGGGGGGGGnnGGGGGGGGGGGGK____",  # 15  nostrils
    # rows 16-17 = mouth (per-turtle, replaced)
    "_____KGGGGGGGGGGGGGGGGGGGGK_____",  # 18  jawline
    "______KGGGGGgggggGGGGGGGGK______",  # 19  chin shadow
]

# ── shared body / shoulders / chest plate (rows 20-31) ─────────
#
# A portrait-framed shoulders + chest plate.  Weapon overlays are
# composited per-turtle below.
_SHARED_BODY = [
    "_______KKGGGGgggggggGGGGKK______",  # 20  neck + collar shadow
    "_____KKGGGGGGGGGGGGGGGGGGGKK____",  # 21  shoulder line begins
    "____KGGGGGGSSSSSSSSSSSSGGGGGGK__",  # 22  shell rim across back
    "___KGGGGGSSSYYYYYYYYYYSSSGGGGGK_",  # 23  upper plastron border
    "___KGGGGSSYYYYYYYYYYYYYYSSGGGGK_",  # 24
    "___KGGGSSYbYYYYYYYYYYYYbYSSGGGK_",  # 25  shoulder straps start
    "___KGGGSYYbyyyyyyyyyyyybYYSGGGK_",  # 26  amber shading lines
    "___KGGGSYYYbyyyyyyyyyybYYYSGGGK_",  # 27
    "___KGGGSYYYYbbyyyyyybbYYYYSGGGK_",  # 28  buckle approach
    "___KGGGSYYYYYBBBBBBBBYYYYYSGGGK_",  # 29  buckle pendant
    "___KGGGSSYYYYYYYYYYYYYYYYSSGGGK_",  # 30  lower plastron
    "___KKKKKSSSSSSSSSSSSSSSSSSKKKKK_",  # 31  shell bottom rim (cropped)
]


# ── Leonardo ───────────────────────────────────────────────────
# Blue bandana, tails streaming to the right. Stern focused eyes
# angled slightly downward toward centre. Flat neutral mouth.
# Two katana hilts peek above the shoulders.

_LEO_BANDANA_TOP = [
    "____KmmmmmmmmmmmmmmmmmmmmmmmmK__",  # 6  bandana top edge
    "____KmmmmmmmmmmmmmmmmmmmmmmmmmK_",  # 7  tail bulges right
]
_LEO_EYES = [
    # Leonardo — focused, slightly angled-down (stern leader)
    # Brow lines slope DOWN toward the centre of the face.
    "____KmmKKKmmmmmmmmmmmmmKKKmmmmmK",  # 8  outer brow ridges
    "____KmKKWWWKmmmmmmmmKWWWKKmmmmmK",  # 9  brow descends inward
    "____KmWWXXWWmmKKmmmWWXXWWmmmmnnK",  # 10 pupils + nose-bridge knot
    "____KmWWXXWWmmmmmmmWWXXWWmmmmnnK",  # 11 lower eye whites
]
_LEO_BANDANA_BOT = [
    "____KmmmmmmmmmmmmmmmmmmmmmmmmmK_",  # 12
    "____KmmmmmmmmmmmmmmmmmmmmmmmmK__",  # 13 (closes back to normal width)
]
_LEO_MOUTH = [
    "______KGGGGGGGGGGGGGGGGGGGGK____",  # 16
    "______KGGGGGGGMMMMMMGGGGGGGK____",  # 17  flat stern mouth
]

_LEO_HEAD = (
    _DOME
    + _LEO_BANDANA_TOP
    + _LEO_EYES
    + _LEO_BANDANA_BOT
    + _FACE_LOWER[:2]
    + _LEO_MOUTH
    + _FACE_LOWER[2:]
)

# Katana hilts peeking above shoulders (overlay applied at rows 20-22)
_LEO_OVERLAY: dict[tuple[int, int], str] = {
    # left katana hilt (above left shoulder)
    (20, 4): "K", (20, 5): "B", (20, 6): "B",
    (21, 4): "K", (21, 5): "u", (21, 6): "B",
    # right katana hilt
    (20, 25): "B", (20, 26): "B", (20, 27): "K",
    (21, 25): "B", (21, 26): "u", (21, 27): "K",
}


# ── Donatello ──────────────────────────────────────────────────
# Purple bandana, tails streaming left. Narrowed analytical eyes.
# Neutral mouth. Diagonal bo staff across the right shoulder.

_DON_BANDANA_TOP = [
    "____KmmmmmmmmmmmmmmmmmmmmmmmmK__",  # 6
    "___KmmmmmmmmmmmmmmmmmmmmmmmmmK__",  # 7  tail bulges LEFT
]
_DON_EYES = [
    # Donatello — narrow analytical eyes, level brows.
    # Squinting / concentrating; eyes are thinner than the others.
    "____KmKKKKmmmmmmmmmmmmKKKKmmmmK_",  # 8  flat thoughtful brow
    "___KmKKWWWKmmmmmmmmmmKWWWKKmmmK_",  # 9  knot+brow on left
    "__KmmWWXXWWmmKKmmmmmWWXXWWmmmnnK",  # 10 small pupils
    "____KmKKKKKmmmmmmmmmmKKKKKmmmnnK",  # 11 narrow lower lid (squint)
]
_DON_BANDANA_BOT = [
    "___KmmmmmmmmmmmmmmmmmmmmmmmmmK__",  # 12
    "____KmmmmmmmmmmmmmmmmmmmmmmmmK__",  # 13
]
_DON_MOUTH = [
    "______KGGGGGGGGGGGGGGGGGGGGK____",  # 16
    "______KGGGGGGGGMMMMGGGGGGGGK____",  # 17  small neutral mouth
]

_DON_HEAD = (
    _DOME
    + _DON_BANDANA_TOP
    + _DON_EYES
    + _DON_BANDANA_BOT
    + _FACE_LOWER[:2]
    + _DON_MOUTH
    + _FACE_LOWER[2:]
)

# Diagonal bō staff overlay — runs from upper-right behind the head
# down past the right shoulder.  Kept off the face/eyes.
_DON_OVERLAY: dict[tuple[int, int], str] = {}
for _r, _c in [
    (3, 29), (4, 29), (5, 28),
    (20, 28), (21, 28), (22, 28),
    (23, 29), (24, 29), (25, 30),
    (26, 30), (27, 30), (28, 31),
]:
    _DON_OVERLAY[(_r, _c)] = "u"
    if _c - 1 >= 0:
        _DON_OVERLAY[(_r, _c - 1)] = "U"  # shadow side of staff


# ── Raphael ────────────────────────────────────────────────────
# Red bandana, tails right. Furious V-shaped angry brows.
# Downturned scowl. Skin reads noticeably darker (via SKIN_TINTS).
# Two sai prongs peek above the shoulders.

_RPH_BANDANA_TOP = [
    "____KmmmmmmmmmmmmmmmmmmmmmmmmK__",  # 6
    "____KmmmmmmmmmmmmmmmmmmmmmmmmmK_",  # 7  tails right
]
_RPH_EYES = [
    # Raphael — the FURIOUS V-brow. Heavy black brow lines
    # plunge down toward the bridge of the nose. Eyes narrow.
    "____KKKKmmmmmmmmmmmmmmmmmmKKKKmK",  # 8  thick outer brow
    "____KmKKKKKmmmmmmmmmmKKKKKmmmmmK",  # 9  inner brow plummets ↘↙
    "____KmmmKKKWXmmmmmmmXWKKKmmmmmnK",  # 10 brow caps the eye
    "____KmmWWXXWmmmmmmmmmWXXWWmmmmnK",  # 11 narrow furious pupils
]
_RPH_BANDANA_BOT = [
    "____KmmmmmmmmmmmmmmmmmmmmmmmmmK_",  # 12
    "____KmmmmmmmmmmmmmmmmmmmmmmmmK__",  # 13
]
_RPH_MOUTH = [
    "______KGGMMMMMMMMMMMMMMGGGGGK___",  # 16  wide angry scowl, downturned
    "______KGGGMMGGGGGGGGMMGGGGGGK___",  # 17  corners drop further
]

_RPH_HEAD = (
    _DOME
    + _RPH_BANDANA_TOP
    + _RPH_EYES
    + _RPH_BANDANA_BOT
    + _FACE_LOWER[:2]
    + _RPH_MOUTH
    + _FACE_LOWER[2:]
)

# Sai prongs above shoulders (steel)
_RPH_OVERLAY: dict[tuple[int, int], str] = {
    # left sai (three prongs: tall centre, short flanking)
    (20, 4): "s", (20, 5): "s", (20, 6): "s",
    (21, 5): "s", (21, 6): "i",
    (22, 5): "i", (22, 6): "B",
    # right sai
    (20, 25): "s", (20, 26): "s", (20, 27): "s",
    (21, 25): "i", (21, 26): "s",
    (22, 25): "B", (22, 26): "i",
}


# ── Michelangelo ───────────────────────────────────────────────
# Orange bandana, tails left. Playful upturned eyes (laughing).
# Big toothy grin. Skin reads lighter / more teal (via SKIN_TINTS).
# Nunchaku handle visible at right shoulder.

_MIK_BANDANA_TOP = [
    "____KmmmmmmmmmmmmmmmmmmmmmmmmK__",  # 6
    "___KmmmmmmmmmmmmmmmmmmmmmmmmmK__",  # 7  tails LEFT
]
_MIK_EYES = [
    # Michelangelo — orange mask, white comic eyes, raised grin energy.
    # The eyes are intentionally blank/white like the reference art.
    "____KmmmKKKKmmmmmmmmKKKKmmmmmmK_",  # 8  raised brow arc
    "___KmKKWWWWKmmmmmmmmKWWWWKKmmmK_",  # 9
    "__KmmWWWWWKmmKKmmmmmKWWWWWmmmnnK",  # 10 blank white eyes
    "____KmKWWWWKmmmmmmmmmKWWWWKmmnnK",  # 11 lower lid arcs UP
]
_MIK_BANDANA_BOT = [
    "___KmmmmmmmmmmmmmmmmmmmmmmmmmK__",  # 12
    "____KmmmmmmmmmmmmmmmmmmmmmmmmK__",  # 13
]
_MIK_MOUTH = [
    "_____KGGMMMMMMMMMMMMMMMMGGGGK___",  # 16  wider black smile line
    "_____KGGMTTTTTTTTTTTTMMGGGGK____",  # 17  big toothy grin
]

_MIK_HEAD = (
    _DOME
    + _MIK_BANDANA_TOP
    + _MIK_EYES
    + _MIK_BANDANA_BOT
    + _FACE_LOWER[:2]
    + _MIK_MOUTH
    + _FACE_LOWER[2:]
)

# Nunchaku across the chest, with a second handle over the right shoulder.
_MIK_OVERLAY: dict[tuple[int, int], str] = {
    (20, 26): "u", (20, 27): "U",
    (21, 26): "u", (21, 27): "U",
    (22, 26): "c",
    (23, 26): "c",
    (24, 5): "u", (24, 6): "U", (24, 23): "u", (24, 24): "U",
    (25, 5): "u", (25, 6): "U", (25, 8): "c", (25, 9): "c", (25, 10): "c",
    (25, 11): "c", (25, 12): "c", (25, 13): "c", (25, 14): "c", (25, 15): "c",
    (25, 16): "c", (25, 17): "c", (25, 20): "c", (25, 23): "u", (25, 24): "U",
    (26, 6): "u", (26, 7): "U", (26, 21): "c", (26, 22): "u", (26, 23): "U",
}


# ── assembled pixel grids ──────────────────────────────────────

_TURTLE_PIXELS: dict[str, list[str]] = {
    "leonardo": _LEO_HEAD + _SHARED_BODY,
    "donatello": _DON_HEAD + _SHARED_BODY,
    "raphael": _RPH_HEAD + _SHARED_BODY,
    "michelangelo": _MIK_HEAD + _SHARED_BODY,
}

_OVERLAYS: dict[str, dict[tuple[int, int], str]] = {
    "leonardo": _LEO_OVERLAY,
    "donatello": _DON_OVERLAY,
    "raphael": _RPH_OVERLAY,
    "michelangelo": _MIK_OVERLAY,
}


def _apply_overlay(
    pixels: list[str], overlay: dict[tuple[int, int], str]
) -> list[str]:
    """Composite weapon overlays on top of the base pixel grid."""
    if not overlay:
        return pixels
    rows = [list(row) for row in pixels]
    for (r, c), ch in overlay.items():
        if 0 <= r < len(rows) and 0 <= c < len(rows[r]):
            rows[r][c] = ch
    return ["".join(row) for row in rows]


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  Renderers
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


def _shade(
    rgb: tuple[int, int, int], factor: float
) -> tuple[int, int, int]:
    """Multiply each channel; clamp to 0-255. Used for bandana shadow."""
    return (
        max(0, min(255, int(rgb[0] * factor))),
        max(0, min(255, int(rgb[1] * factor))),
        max(0, min(255, int(rgb[2] * factor))),
    )


def _tint(
    rgb: tuple[int, int, int], delta: tuple[int, int, int]
) -> tuple[int, int, int]:
    """Add per-channel offset; clamp to 0-255. Used for skin tinting."""
    return (
        max(0, min(255, rgb[0] + delta[0])),
        max(0, min(255, rgb[1] + delta[1])),
        max(0, min(255, rgb[2] + delta[2])),
    )


def _color_for(
    char: str,
    bandana: tuple[int, int, int],
    skin_delta: tuple[int, int, int],
) -> tuple[int, int, int] | None:
    if char == "m":
        return bandana
    base = PALETTE.get(char)
    if base is None:
        return None
    if char in _SKIN_KEYS and skin_delta != (0, 0, 0):
        return _tint(base, skin_delta)
    return base


def _render_plain(pixels: list[str]) -> str:
    """Half-block render without colour (backward compat)."""
    pw = len(pixels[0])
    pad_l = (FRAME_WIDTH - pw) // 2
    pad_r = FRAME_WIDTH - pw - pad_l
    lines: list[str] = []
    for i in range(0, len(pixels), 2):
        top, bot = pixels[i], pixels[i + 1]
        row: list[str] = []
        for j in range(pw):
            tf, bf = top[j] != "_", bot[j] != "_"
            if tf and bf:
                row.append("█")
            elif tf:
                row.append("▀")
            elif bf:
                row.append("▄")
            else:
                row.append(" ")
        lines.append(" " * pad_l + "".join(row) + " " * pad_r)
    return "\n".join(lines)


def _render_rich(
    pixels: list[str],
    bandana: tuple[int, int, int],
    skin_delta: tuple[int, int, int],
) -> list[Text]:
    """Half-block render with per-pixel RGB colour via Rich."""
    pw = len(pixels[0])
    pad_l = (FRAME_WIDTH - pw) // 2
    pad_r = FRAME_WIDTH - pw - pad_l
    lines: list[Text] = []

    for i in range(0, len(pixels), 2):
        top_row, bot_row = pixels[i], pixels[i + 1]
        text = Text()
        text.append(" " * pad_l)

        for j in range(pw):
            tc = _color_for(top_row[j], bandana, skin_delta)
            bc = _color_for(bot_row[j], bandana, skin_delta)

            if tc is None and bc is None:
                text.append(" ")
            elif tc is not None and bc is None:
                r, g, b = tc
                text.append("▀", style=f"rgb({r},{g},{b})")
            elif tc is None and bc is not None:
                r, g, b = bc
                text.append("▄", style=f"rgb({r},{g},{b})")
            elif tc == bc:
                r, g, b = tc  # type: ignore[misc]
                text.append("█", style=f"rgb({r},{g},{b})")
            else:
                tr, tg, tb = tc  # type: ignore[misc]
                br, bg, bb = bc  # type: ignore[misc]
                text.append(
                    "▀",
                    style=f"rgb({tr},{tg},{tb}) on rgb({br},{bg},{bb})",
                )

        text.append(" " * pad_r)
        lines.append(text)

    return lines


def _pt_style(rgb: tuple[int, int, int], *, background: bool = False) -> str:
    prefix = "bg:" if background else ""
    return f"{prefix}#{rgb[0]:02x}{rgb[1]:02x}{rgb[2]:02x}"


def _render_prompt_toolkit(
    pixels: list[str],
    bandana: tuple[int, int, int],
    skin_delta: tuple[int, int, int],
) -> list[tuple[str, str]]:
    """Half-block render with prompt-toolkit-compatible RGB fragments."""
    pw = len(pixels[0])
    pad_l = (FRAME_WIDTH - pw) // 2
    pad_r = FRAME_WIDTH - pw - pad_l
    fragments: list[tuple[str, str]] = []

    for i in range(0, len(pixels), 2):
        top_row, bot_row = pixels[i], pixels[i + 1]
        fragments.append(("", " " * pad_l))

        for j in range(pw):
            tc = _color_for(top_row[j], bandana, skin_delta)
            bc = _color_for(bot_row[j], bandana, skin_delta)

            if tc is None and bc is None:
                fragments.append(("", " "))
            elif tc is not None and bc is None:
                fragments.append((_pt_style(tc), "▀"))
            elif tc is None and bc is not None:
                fragments.append((_pt_style(bc), "▄"))
            elif tc == bc:
                fragments.append((_pt_style(tc), "█"))  # type: ignore[arg-type]
            else:
                fragments.append((f"{_pt_style(tc)} {_pt_style(bc, background=True)}", "▀"))  # type: ignore[arg-type]

        fragments.append(("", " " * pad_r + "\n"))

    return fragments



def frame_count(activity: str) -> int:
    return 3 if activity == "work" else 2


def _pixels_for(name: str) -> list[str]:
    key = name if name in _TURTLE_PIXELS else "leonardo"
    grid = list(_TURTLE_PIXELS[key])
    return _apply_overlay(grid, _OVERLAYS.get(key, {}))


def mascot_frame(
    mode: TurtleMode, frame: int = 0, activity: str = "idle"
) -> str:
    """Plain-text mascot frame (backward compat)."""
    return _render_plain(_pixels_for(mode.key))


def mascot_rich_lines(
    mode: TurtleMode, frame: int = 0, activity: str = "idle"
) -> list[Text]:
    """Full-colour Rich Text lines for the mascot."""
    name = mode.key if mode.key in _TURTLE_PIXELS else "leonardo"
    pixels = _pixels_for(name)
    bandana = BANDANA_COLORS.get(name, BANDANA_COLORS["leonardo"])
    skin_delta = SKIN_TINTS.get(name, (0, 0, 0))
    return _render_rich(pixels, bandana, skin_delta)


def mascot_prompt_fragments(
    mode: TurtleMode, frame: int = 0, activity: str = "idle"
) -> list[tuple[str, str]]:
    """Full-colour prompt-toolkit fragments for interactive selector previews."""
    name = mode.key if mode.key in _TURTLE_PIXELS else "leonardo"
    pixels = _pixels_for(name)
    bandana = BANDANA_COLORS.get(name, BANDANA_COLORS["leonardo"])
    skin_delta = SKIN_TINTS.get(name, (0, 0, 0))
    return _render_prompt_toolkit(pixels, bandana, skin_delta)
