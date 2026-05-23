from turtles_cli.providers import PROVIDERS


def test_default_models_are_current_generation() -> None:
    assert PROVIDERS["openai"].default_models[0] == "gpt-5.2"
    assert PROVIDERS["anthropic"].default_models[0] == "claude-sonnet-4-6"
    assert PROVIDERS["xai"].default_models[0] == "grok-4.3-latest"


def test_openrouter_defaults_are_free_models() -> None:
    assert PROVIDERS["openrouter"].default_models[0] == "openrouter/free"
    assert all(model == "openrouter/free" or model.endswith(":free") for model in PROVIDERS["openrouter"].default_models)


def test_custom_provider_supports_openai_compatible_base_url() -> None:
    provider = PROVIDERS["custom"]

    assert provider.requires_base_url is True
    assert provider.protocol == "openai"
