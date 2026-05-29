from prompt_toolkit.document import Document

from turtles_cli.prompting import ProjectCompleter, SlashCommandCompleter


def test_slash_completer_replaces_single_slash() -> None:
    completions = list(SlashCommandCompleter().get_completions(Document("/"), None))
    login = next(completion for completion in completions if completion.text == "/login")

    assert login.start_position == -1


def test_slash_completer_replaces_partial_command() -> None:
    completions = list(SlashCommandCompleter().get_completions(Document("/lo"), None))
    login = next(completion for completion in completions if completion.text == "/login")

    assert login.start_position == -3


def test_project_completer_suggests_at_file_mentions(tmp_path) -> None:
    source = tmp_path / "turtles_cli" / "commands.py"
    source.parent.mkdir()
    source.write_text("print('ok')\n", encoding="utf-8")

    completions = list(ProjectCompleter(tmp_path).get_completions(Document("review @comm"), None))
    mention = next(completion for completion in completions if completion.text == "@turtles_cli/commands.py")

    assert mention.start_position == -5


def test_project_completer_suggests_files_after_bare_at(tmp_path) -> None:
    source = tmp_path / "README.md"
    source.write_text("# Project\n", encoding="utf-8")

    completions = list(ProjectCompleter(tmp_path).get_completions(Document("review @"), None))
    mention = next(completion for completion in completions if completion.text == "@README.md")

    assert mention.start_position == -1


def test_project_completer_suggests_files_inside_slash_commands(tmp_path) -> None:
    source = tmp_path / "README.md"
    source.write_text("# Project\n", encoding="utf-8")

    completions = list(ProjectCompleter(tmp_path).get_completions(Document("/simulation @"), None))
    mention = next(completion for completion in completions if completion.text == "@README.md")

    assert mention.start_position == -1
