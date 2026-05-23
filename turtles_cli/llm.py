from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import httpx

from .config import TurtlesConfig, is_logged_in
from .providers import PROVIDERS, Provider


class LLMError(RuntimeError):
    pass


@dataclass(frozen=True)
class LLMResponse:
    text: str
    provider: str
    model: str


Message = dict[str, str]


def provider_ready(config: TurtlesConfig) -> bool:
    return is_logged_in(config) and config.provider.model != ""


def complete_text(config: TurtlesConfig, system: str, prompt: str, *, timeout: float = 45.0) -> LLMResponse:
    if not provider_ready(config):
        raise LLMError("No provider/model is configured. Run /login first.")

    provider = PROVIDERS.get(config.provider.provider)
    if provider is None:
        raise LLMError(f"Unknown provider: {config.provider.provider}")
    if provider.protocol == "bedrock":
        raise LLMError("AWS Bedrock needs a signed SDK transport; use Custom OpenAI-compatible for gateways.")

    messages = [{"role": "system", "content": system}, {"role": "user", "content": prompt}]
    if provider.protocol == "anthropic":
        text = _anthropic_complete(provider, config, messages, timeout)
    elif provider.protocol == "gemini":
        text = _gemini_complete(provider, config, messages, timeout)
    elif provider.protocol == "ollama":
        text = _ollama_complete(provider, config, messages, timeout)
    else:
        text = _openai_compatible_complete(provider, config, messages, timeout)
    return LLMResponse(text=text.strip(), provider=provider.label, model=config.provider.model)


def _base_url(provider: Provider, config: TurtlesConfig) -> str:
    base_url = (config.provider.base_url or provider.base_url).rstrip("/")
    if provider.requires_base_url and not base_url:
        raise LLMError(f"{provider.label} requires a base URL. Run /provider and set one.")
    if not base_url:
        raise LLMError(f"{provider.label} has no API base URL configured.")
    return base_url


def _headers(provider: Provider, api_key: str) -> dict[str, str]:
    headers = {"Content-Type": "application/json"}
    if provider.key == "azure-openai":
        headers["api-key"] = api_key
    elif api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    if provider.key == "openrouter":
        headers["HTTP-Referer"] = "https://github.com/turtles-cli/turtles-cli"
        headers["X-Title"] = "Turtles CLI"
    return headers


def _openai_compatible_complete(provider: Provider, config: TurtlesConfig, messages: list[Message], timeout: float) -> str:
    base_url = _base_url(provider, config)
    if provider.key == "azure-openai" and "/deployments/" not in base_url:
        url = f"{base_url}/openai/deployments/{config.provider.model}/chat/completions?api-version=2025-04-01-preview"
        model_payload: dict[str, Any] = {}
    else:
        url = f"{base_url}/chat/completions"
        model_payload = {"model": config.provider.model}
    payload: dict[str, Any] = {
        **model_payload,
        "messages": messages,
        "temperature": 0.2,
        "max_tokens": 1400,
    }
    data = _post_json(url, payload, _headers(provider, config.provider.api_key), timeout)
    try:
        return str(data["choices"][0]["message"]["content"])
    except (KeyError, IndexError, TypeError) as exc:
        raise LLMError(f"Unexpected {provider.label} response shape.") from exc


def _anthropic_complete(provider: Provider, config: TurtlesConfig, messages: list[Message], timeout: float) -> str:
    user_message = "\n\n".join(message["content"] for message in messages if message["role"] == "user")
    system = "\n\n".join(message["content"] for message in messages if message["role"] == "system")
    payload = {
        "model": config.provider.model,
        "system": system,
        "messages": [{"role": "user", "content": user_message}],
        "max_tokens": 1400,
        "temperature": 0.2,
    }
    headers = {
        "Content-Type": "application/json",
        "x-api-key": config.provider.api_key,
        "anthropic-version": "2023-06-01",
    }
    data = _post_json(f"{_base_url(provider, config)}/messages", payload, headers, timeout)
    try:
        parts = data["content"]
        return "\n".join(str(part.get("text", "")) for part in parts if part.get("type") == "text")
    except (KeyError, TypeError) as exc:
        raise LLMError("Unexpected Anthropic response shape.") from exc


def _gemini_complete(provider: Provider, config: TurtlesConfig, messages: list[Message], timeout: float) -> str:
    prompt = "\n\n".join(f"{message['role'].title()}:\n{message['content']}" for message in messages)
    url = f"{_base_url(provider, config)}/models/{config.provider.model}:generateContent?key={config.provider.api_key}"
    payload = {
        "contents": [{"role": "user", "parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": 0.2, "maxOutputTokens": 1400},
    }
    data = _post_json(url, payload, {"Content-Type": "application/json"}, timeout)
    try:
        parts = data["candidates"][0]["content"]["parts"]
        return "\n".join(str(part.get("text", "")) for part in parts)
    except (KeyError, IndexError, TypeError) as exc:
        raise LLMError("Unexpected Gemini response shape.") from exc


def _ollama_complete(provider: Provider, config: TurtlesConfig, messages: list[Message], timeout: float) -> str:
    base_url = (config.provider.api_key or config.provider.base_url or provider.base_url).rstrip("/")
    payload = {"model": config.provider.model, "messages": messages, "stream": False}
    data = _post_json(f"{base_url}/api/chat", payload, {"Content-Type": "application/json"}, timeout)
    try:
        return str(data["message"]["content"])
    except (KeyError, TypeError) as exc:
        raise LLMError("Unexpected Ollama response shape.") from exc


def _post_json(url: str, payload: dict[str, Any], headers: dict[str, str], timeout: float) -> dict[str, Any]:
    try:
        with httpx.Client(timeout=timeout, follow_redirects=True) as client:
            response = client.post(url, json=payload, headers=headers)
            response.raise_for_status()
            return response.json()
    except httpx.HTTPStatusError as exc:
        detail = exc.response.text[:400]
        raise LLMError(f"Provider request failed with HTTP {exc.response.status_code}: {detail}") from exc
    except (httpx.HTTPError, ValueError) as exc:
        raise LLMError(f"Provider request failed: {exc}") from exc
