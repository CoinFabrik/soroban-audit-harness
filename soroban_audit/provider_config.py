#!/usr/bin/env python3
"""Provider/model configuration shared by the audit harness runners."""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any


DEFAULT_OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
DEFAULT_OPENROUTER_KEY_ENV = "OPENROUTER_API_KEY"
MODEL_CONTEXT_WINDOW_ENV = "HARNESS_MODEL_CONTEXT_WINDOW"
REASONING_EFFORTS = ("none", "minimal", "low", "medium", "high", "xhigh")
_SAFE_COMPONENT = re.compile(r"[^A-Za-z0-9._:-]+")


def _toml_string(value: str) -> str:
    # JSON strings are valid TOML basic strings for the values used here.
    return json.dumps(value, ensure_ascii=False)


def safe_component(value: str) -> str:
    """Return a filesystem-safe, non-traversing path component."""
    cleaned = _SAFE_COMPONENT.sub("-", value.strip()).strip("-.")
    if not cleaned or cleaned in {".", ".."}:
        raise ValueError(f"Unsafe empty path component derived from {value!r}")
    return cleaned


@dataclass(frozen=True)
class RunConfiguration:
    provider: str
    model: str
    reasoning_effort: str
    provider_base_url: str | None = None
    provider_api_key_env: str | None = None

    @classmethod
    def create(
        cls,
        *,
        provider: str,
        model: str,
        reasoning_effort: str,
        provider_base_url: str | None = None,
        provider_api_key_env: str | None = None,
    ) -> "RunConfiguration":
        if provider not in {"codex-default", "openrouter"}:
            raise ValueError(f"Unsupported provider: {provider}")
        if not model.strip():
            raise ValueError("Model must not be empty")
        if reasoning_effort not in REASONING_EFFORTS:
            raise ValueError(
                f"Unsupported reasoning effort {reasoning_effort!r}; "
                f"choose one of {', '.join(REASONING_EFFORTS)}"
            )
        if provider == "codex-default":
            if provider_base_url or provider_api_key_env:
                raise ValueError("Provider URL/key options apply only to OpenRouter")
            return cls(provider, model.strip(), reasoning_effort)
        return cls(
            provider,
            model.strip(),
            reasoning_effort,
            (provider_base_url or DEFAULT_OPENROUTER_BASE_URL).rstrip("/"),
            provider_api_key_env or DEFAULT_OPENROUTER_KEY_ENV,
        )

    @property
    def path_parts(self) -> tuple[str, ...]:
        model_parts = tuple(safe_component(part) for part in self.model.split("/") if part)
        if not model_parts:
            raise ValueError("Model must contain at least one usable path component")
        return (
            safe_component(self.provider),
            *model_parts,
            safe_component(self.reasoning_effort),
        )

    @property
    def configuration_id(self) -> str:
        return "--".join(self.path_parts)

    def run_root(self, base: Path) -> Path:
        return base.joinpath(*self.path_parts)

    def identity(self) -> dict[str, Any]:
        return {
            "provider": self.provider,
            "providerBaseUrl": self.provider_base_url,
            "providerApiKeyEnv": self.provider_api_key_env,
            "model": self.model,
            "reasoningEffort": self.reasoning_effort,
            "runConfigurationId": self.configuration_id,
        }

    def validate_environment(self) -> None:
        if self.provider_api_key_env and not os.environ.get(self.provider_api_key_env):
            raise RuntimeError(
                f"{self.provider_api_key_env} is not set. Export the OpenRouter API key "
                "before starting a paid harness run."
            )

    def codex_config_args(self) -> list[str]:
        args: list[str] = []
        if self.provider == "openrouter":
            args.extend(
                [
                    "-c",
                    'model_provider="openrouter"',
                    "-c",
                    'model_providers.openrouter.name="OpenRouter"',
                    "-c",
                    f"model_providers.openrouter.base_url={_toml_string(self.provider_base_url or '')}",
                    "-c",
                    f"model_providers.openrouter.env_key={_toml_string(self.provider_api_key_env or '')}",
                    "-c",
                    'model_providers.openrouter.wire_api="responses"',
                    "-c",
                    "model_providers.openrouter.supports_websockets=false",
                ]
            )
        if self.reasoning_effort != "none":
            args.extend(["-c", f'model_reasoning_effort="{self.reasoning_effort}"'])
        model_context_window = os.environ.get(MODEL_CONTEXT_WINDOW_ENV)
        if model_context_window:
            try:
                parsed_context_window = int(model_context_window)
            except ValueError as exc:
                raise ValueError(
                    f"{MODEL_CONTEXT_WINDOW_ENV} must be a positive integer"
                ) from exc
            if parsed_context_window <= 0:
                raise ValueError(
                    f"{MODEL_CONTEXT_WINDOW_ENV} must be a positive integer"
                )
            args.extend(["-c", f"model_context_window={parsed_context_window}"])
        return args

    def codex_exec_prefix(self, codex: str) -> list[str]:
        return [
            codex,
            "exec",
            "--ephemeral",
            "--ignore-user-config",
            "--ignore-rules",
            "--skip-git-repo-check",
            "--approve-for-me",
            "--color",
            "never",
            "--model",
            self.model,
            *self.codex_config_args(),
        ]


def add_provider_arguments(parser: Any) -> None:
    parser.add_argument(
        "--provider",
        choices=("codex-default", "openrouter"),
        default="codex-default",
        help="Use the normal Codex provider or route Codex through OpenRouter.",
    )
    parser.add_argument("--model", default="gpt-5.6-sol")
    parser.add_argument(
        "--reasoning-effort",
        choices=REASONING_EFFORTS,
        default="high",
        help="Use 'none' to avoid sending a reasoning override to models that do not support it.",
    )
    parser.add_argument(
        "--provider-base-url",
        help=f"OpenRouter-compatible base URL (default: {DEFAULT_OPENROUTER_BASE_URL}).",
    )
    parser.add_argument(
        "--provider-api-key-env",
        help=f"Environment variable containing the provider key (default: {DEFAULT_OPENROUTER_KEY_ENV}).",
    )


def configuration_from_args(args: Any) -> RunConfiguration:
    return RunConfiguration.create(
        provider=args.provider,
        model=args.model,
        reasoning_effort=args.reasoning_effort,
        provider_base_url=args.provider_base_url,
        provider_api_key_env=args.provider_api_key_env,
    )


def validate_manifest_identity(manifest: dict[str, Any], config: RunConfiguration) -> None:
    mismatches = []
    for key, expected in config.identity().items():
        if manifest.get(key) != expected:
            mismatches.append(f"{key}: found {manifest.get(key)!r}, expected {expected!r}")
    if mismatches:
        raise RuntimeError(
            "Existing run manifest belongs to a different configuration:\n  "
            + "\n  ".join(mismatches)
        )
