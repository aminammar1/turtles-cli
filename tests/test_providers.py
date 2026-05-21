from turtles_cli.providers import PROVIDERS


def test_default_models_are_current_generation() -> None:
    assert PROVIDERS["openai"].default_models[0] == "gpt-5.2"
    assert PROVIDERS["anthropic"].default_models[0] == "claude-sonnet-4-6"
    assert PROVIDERS["xai"].default_models[0] == "grok-4.3"
