from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Provider:
    key: str
    label: str
    default_models: tuple[str, ...]
    env_var: str
    base_url: str = ""
    context_window: int = 128_000
    protocol: str = "openai"
    requires_base_url: bool = False


PROVIDERS: dict[str, Provider] = {
    "openrouter": Provider(
        "openrouter",
        "OpenRouter",
        (
            "openrouter/free",
            "nvidia/nemotron-3-super-120b-a12b:free",
            "poolside/laguna-m.1:free",
            "deepseek/deepseek-v4-flash:free",
            "openai/gpt-oss-120b:free",
            "z-ai/glm-4.5-air:free",
        ),
        "OPENROUTER_API_KEY",
        "https://openrouter.ai/api/v1",
        1_048_576,
    ),
    "anthropic": Provider(
        "anthropic",
        "Anthropic",
        ("claude-sonnet-4-6", "claude-opus-4-7", "claude-haiku-4-5-20251001"),
        "ANTHROPIC_API_KEY",
        "https://api.anthropic.com/v1",
        200_000,
        "anthropic",
    ),
    "openai": Provider(
        "openai",
        "OpenAI",
        ("gpt-5.2", "gpt-5.2-pro", "gpt-5.2-codex", "gpt-5.2-chat-latest", "gpt-5-mini", "gpt-oss-120b"),
        "OPENAI_API_KEY",
        "https://api.openai.com/v1",
        1_048_576,
    ),
    "google": Provider(
        "google",
        "Google Gemini",
        ("gemini-3-pro-preview", "gemini-3-flash-preview", "gemini-pro-latest", "gemini-flash-latest"),
        "GOOGLE_API_KEY",
        "https://generativelanguage.googleapis.com/v1beta",
        1_048_576,
        "gemini",
    ),
    "bedrock": Provider(
        "bedrock",
        "AWS Bedrock",
        ("anthropic.claude-sonnet-4-6", "anthropic.claude-opus-4-7", "anthropic.claude-haiku-4-5-20251001-v1:0"),
        "AWS_ACCESS_KEY_ID",
        context_window=200_000,
        protocol="bedrock",
    ),
    "nvidia": Provider(
        "nvidia",
        "NVIDIA AI",
        ("nvidia/llama-3.3-nemotron-super-49b-v1.5", "nvidia/nemotron-3-super-120b-a12b", "nvidia/nemotron-3-nano-30b-a3b"),
        "NVIDIA_API_KEY",
        "https://integrate.api.nvidia.com/v1",
        1_048_576,
    ),
    "xai": Provider("xai", "xAI (Grok)", ("grok-4.3-latest", "grok-4.3"), "XAI_API_KEY", "https://api.x.ai/v1", 256_000),
    "azure-openai": Provider(
        "azure-openai",
        "Azure OpenAI",
        ("gpt-5.2", "gpt-5.2-codex", "gpt-5-mini"),
        "AZURE_OPENAI_API_KEY",
        context_window=1_048_576,
        requires_base_url=True,
    ),
    "ollama": Provider("ollama", "Ollama (local)", ("qwen3:8b", "llama4:scout", "deepseek-r1:32b", "gemma3:12b"), "OLLAMA_HOST", "http://127.0.0.1:11434", 131_072, "ollama"),
    "custom": Provider(
        "custom",
        "Custom OpenAI-compatible",
        ("model-name",),
        "CUSTOM_LLM_API_KEY",
        context_window=128_000,
        requires_base_url=True,
    ),
}


def provider_choices() -> list[str]:
    return [provider.label for provider in PROVIDERS.values()]


def provider_from_label(label_or_key: str) -> Provider | None:
    normalized = label_or_key.strip().lower()
    if normalized in PROVIDERS:
        return PROVIDERS[normalized]
    for provider in PROVIDERS.values():
        if provider.label.lower() == normalized:
            return provider
    return None


def detect_provider_from_key(api_key: str) -> Provider | None:
    if api_key.startswith("sk-or-"):
        return PROVIDERS["openrouter"]
    if api_key.startswith("sk-ant-"):
        return PROVIDERS["anthropic"]
    if api_key.startswith("sk-"):
        return PROVIDERS["openai"]
    return None
