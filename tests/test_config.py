from turtles_cli.config import ProviderConfig, TurtlesConfig, load_config, save_config


def test_config_round_trip(tmp_path) -> None:
    config = TurtlesConfig(trusted=True, mode="raphael", provider=ProviderConfig(provider="custom", model="my-model", base_url="https://llm.example/v1"))
    save_config(config, tmp_path)
    loaded = load_config(tmp_path)

    assert loaded.trusted is True
    assert loaded.mode == "raphael"
    assert loaded.provider.base_url == "https://llm.example/v1"
    assert "github" in loaded.mcp_servers
