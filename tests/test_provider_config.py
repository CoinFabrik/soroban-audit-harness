from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from soroban_audit.provider_config import RunConfiguration, validate_manifest_identity


class ProviderConfigurationTests(unittest.TestCase):
    def test_openrouter_identity_and_path(self) -> None:
        config = RunConfiguration.create(
            provider="openrouter",
            model="anthropic/example-model",
            reasoning_effort="none",
        )
        self.assertEqual(
            config.run_root(Path("runs")),
            Path("runs/openrouter/anthropic/example-model/none"),
        )
        rendered = " ".join(config.codex_exec_prefix("codex"))
        self.assertIn('model_provider="openrouter"', rendered)
        self.assertIn("--sandbox workspace-write", rendered)
        self.assertNotIn("dangerously-bypass", rendered)

    def test_openrouter_requires_key(self) -> None:
        config = RunConfiguration.create(
            provider="openrouter",
            model="vendor/model",
            reasoning_effort="high",
            provider_api_key_env="HARNESS_TEST_KEY",
        )
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaisesRegex(RuntimeError, "HARNESS_TEST_KEY"):
                config.validate_environment()

    def test_context_window_override(self) -> None:
        config = RunConfiguration.create(
            provider="openrouter",
            model="vendor/model",
            reasoning_effort="high",
        )
        with patch.dict(os.environ, {"HARNESS_MODEL_CONTEXT_WINDOW": "65536"}):
            self.assertIn("model_context_window=65536", " ".join(config.codex_config_args()))

    def test_resume_rejects_different_model(self) -> None:
        old = RunConfiguration.create(
            provider="codex-default", model="model-a", reasoning_effort="high"
        )
        new = RunConfiguration.create(
            provider="codex-default", model="model-b", reasoning_effort="high"
        )
        with self.assertRaisesRegex(RuntimeError, "different configuration"):
            validate_manifest_identity(old.identity(), new)

    def test_model_path_cannot_escape_output_root(self) -> None:
        config = RunConfiguration.create(
            provider="openrouter",
            model="vendor/a model:free",
            reasoning_effort="low",
        )
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = config.run_root(Path(temporary_directory)).resolve()
            self.assertTrue(root.is_relative_to(Path(temporary_directory).resolve()))


if __name__ == "__main__":
    unittest.main()
