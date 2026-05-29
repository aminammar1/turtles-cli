from turtles_cli.mascots import MASCOTS, mascot_frame, mascot_prompt_fragments
from turtles_cli.modes import MODES
from turtles_cli.ui import mode_choice_preview


def test_mascot_frames_keep_stable_dimensions() -> None:
    expected_shape: tuple[int, int] | None = None
    for mode in MODES.values():
        assert mode.key in MASCOTS
        for activity in ("idle", "work", "battle"):
            for index in range(3):
                lines = mascot_frame(mode, index, activity).splitlines()
                shape = (len(lines), len(lines[0]))
                assert all(len(line) == shape[1] for line in lines)
                expected_shape = expected_shape or shape
                assert shape == expected_shape


def test_mode_preview_shows_current_mascot_art() -> None:
    preview = "".join(text for _style, text in mode_choice_preview("Michelangelo - Creative and fun; experiments"))

    assert "Michelangelo" in preview
    assert "████" in preview or "▀▀▀▀" in preview
    assert "/simulation" not in preview


def test_prompt_toolkit_mascot_uses_actual_colored_fragments() -> None:
    fragments = mascot_prompt_fragments(MODES["michelangelo"])
    styles = {style for style, text in fragments if text.strip()}
    lines = "".join(text for _style, text in fragments).splitlines()
    plain_lines = mascot_frame(MODES["michelangelo"]).splitlines()

    assert len(lines) == len(plain_lines)
    assert all(len(line) == len(plain_lines[0]) for line in lines)
    assert any("#ff9800" in style for style in styles)
    assert len(styles) > 4
