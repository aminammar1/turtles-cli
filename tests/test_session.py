from turtles_cli.session import load_cache, record_command, save_cache


def test_session_cache_records_recent_commands(tmp_path) -> None:
    record_command(tmp_path, "/help", mode="leonardo", provider="openai", model="gpt-5.2")
    cache = load_cache(tmp_path)

    assert cache.last_mode == "leonardo"
    assert cache.last_provider == "openai"
    assert cache.last_model == "gpt-5.2"
    assert cache.recent_commands == ["/help"]


def test_session_cache_preserves_project_context(tmp_path) -> None:
    cache = load_cache(tmp_path)
    cache.project_context_key = "k"
    cache.project_context = "cached files"
    save_cache(cache, tmp_path)
    loaded = load_cache(tmp_path)

    assert loaded.project_context_key == "k"
    assert loaded.project_context == "cached files"
