def test_cli_modules_import() -> None:
    from turtles_cli.main import app
    from turtles_cli.ui import choose_mode, render_header

    assert app is not None
    assert choose_mode is not None
    assert render_header is not None
