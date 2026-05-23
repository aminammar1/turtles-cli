from turtles_cli.mascots import MASCOTS, mascot_frame
from turtles_cli.modes import MODES


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
