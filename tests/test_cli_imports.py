def test_cli_modules_import() -> None:
    from turtles_cli.main import app
    from turtles_cli.ui import choose_mode, render_header

    assert app is not None
    assert choose_mode is not None
    assert render_header is not None


def test_turtle_console_script_is_declared() -> None:
    import tomllib
    from pathlib import Path

    pyproject = tomllib.loads((Path(__file__).parents[1] / "pyproject.toml").read_text(encoding="utf-8"))

    assert pyproject["project"]["scripts"]["turtle"] == "turtles_cli.main:app"
