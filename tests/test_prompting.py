from prompt_toolkit.document import Document

from turtles_cli.prompting import SlashCommandCompleter


def test_slash_completer_replaces_single_slash() -> None:
    completions = list(SlashCommandCompleter().get_completions(Document("/"), None))
    login = next(completion for completion in completions if completion.text == "/login")

    assert login.start_position == -1


def test_slash_completer_replaces_partial_command() -> None:
    completions = list(SlashCommandCompleter().get_completions(Document("/lo"), None))
    login = next(completion for completion in completions if completion.text == "/login")

    assert login.start_position == -3
