from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Provider:
    key: str
    label: str
    default_models: tuple[str, ...]
    env_var: str


PROVIDERS: dict[str, Provider] = {
    "openrouter": Provider(
        "openrouter",
        "OpenRouter",
        ("openai/gpt-5.2", "anthropic/claude-sonnet-4.6", "google/gemini-3-pro-preview", "x-ai/grok-4.3"),
        "OPENROUTER_API_KEY",
    ),
    "anthropic": Provider(
        "anthropic",
        "Anthropic",
        ("claude-sonnet-4-6", "claude-opus-4-7", "claude-haiku-4-5-20251001"),
        "ANTHROPIC_API_KEY",
    ),
    "openai": Provider("openai", "OpenAI", ("gpt-5.2", "gpt-5.2-codex", "gpt-5-mini", "gpt-oss-120b"), "OPENAI_API_KEY"),
    "google": Provider("google", "Google Gemini", ("gemini-3-pro-preview", "gemini-2.5-pro", "gemini-2.5-flash"), "GOOGLE_API_KEY"),
    "bedrock": Provider(
        "bedrock",
        "AWS Bedrock",
        ("anthropic.claude-sonnet-4-6", "anthropic.claude-opus-4-7", "anthropic.claude-haiku-4-5-20251001-v1:0"),
        "AWS_ACCESS_KEY_ID",
    ),
    "nvidia": Provider(
        "nvidia",
        "NVIDIA AI",
        ("nvidia/llama-3.3-nemotron-super-49b-v1.5", "nvidia/nemotron-3-super-120b-a12b", "nvidia/nemotron-3-nano-30b-a3b"),
        "NVIDIA_API_KEY",
    ),
    "xai": Provider("xai", "xAI (Grok)", ("grok-4.3", "grok-4.3-latest"), "XAI_API_KEY"),
    "azure-openai": Provider("azure-openai", "Azure OpenAI", ("gpt-5.2", "gpt-5.2-codex", "gpt-5-mini"), "AZURE_OPENAI_API_KEY"),
    "ollama": Provider("ollama", "Ollama (local)", ("qwen3:8b", "llama4:scout", "deepseek-r1:32b", "gemma3:12b"), "OLLAMA_HOST"),
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
