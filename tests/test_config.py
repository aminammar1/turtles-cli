from turtles_cli.config import TurtlesConfig, load_config, save_config


def test_config_round_trip(tmp_path) -> None:
    config = TurtlesConfig(trusted=True, mode="raphael")
    save_config(config, tmp_path)
    loaded = load_config(tmp_path)

    assert loaded.trusted is True
    assert loaded.mode == "raphael"
    assert "github" in loaded.mcp_servers
