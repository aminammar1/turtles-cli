from turtles_cli.audits import context_usage


def test_context_usage_returns_claude_style_categories() -> None:
    usage = context_usage(["hello world"], window=200_000, model="test-model")

    assert usage["model"] == "test-model"
    assert usage["window"] == 200_000
    assert usage["categories"]["system_prompt"] > 0
    assert usage["autocompact_buffer"] > 0
