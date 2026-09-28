from __future__ import annotations

import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from soroban_audit.provider_config import RunConfiguration
from soroban_audit.runner import scan_repository


ROOT = Path(__file__).resolve().parents[1]
FAKE_CODEX = ROOT / "tests" / "fake_codex.py"


def make_repository(root: Path) -> tuple[Path, str]:
    repository = root / "fixture"
    (repository / "src").mkdir(parents=True)
    (repository / "src" / "lib.rs").write_text("pub fn value() -> u32 { 1 }\n", encoding="utf-8")
    subprocess.run(["git", "init", "-q", str(repository)], check=True)
    subprocess.run(["git", "-C", str(repository), "config", "user.name", "Test"], check=True)
    subprocess.run(
        ["git", "-C", str(repository), "config", "user.email", "test@example.com"],
        check=True,
    )
    subprocess.run(["git", "-C", str(repository), "add", "src/lib.rs"], check=True)
    subprocess.run(["git", "-C", str(repository), "commit", "-qm", "fixture"], check=True)
    revision = subprocess.run(
        ["git", "-C", str(repository), "rev-parse", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    return repository, revision


class RunnerTests(unittest.TestCase):
    def run_scan(self, harness: str) -> tuple[Path, Path, Path]:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name)
        repository, revision = make_repository(root)
        capture = root / "captures"
        invocation_log = root / "invocations.log"
        config = RunConfiguration.create(
            provider="codex-default",
            model="test-model",
            reasoning_effort="high",
        )
        with patch.dict(
            os.environ,
            {
                "FAKE_CODEX_CAPTURE_DIR": str(capture),
                "FAKE_CODEX_INVOCATION_LOG": str(invocation_log),
            },
        ):
            run_dir = scan_repository(
                repository=repository,
                reference=revision,
                harness=harness,
                output_root=root / "runs",
                codex=str(FAKE_CODEX),
                config=config,
                additional_knowledge_dirs=[],
                retries=0,
                timeout_seconds=30,
                rate_limit_retries=0,
                rate_limit_cooldown_seconds=0,
            )
        return run_dir, capture, invocation_log

    def test_h1_runs_without_h2_knowledge(self) -> None:
        run_dir, capture, _ = self.run_scan("h1")
        self.assertTrue((run_dir / "h1-validated.json").is_file())
        self.assertFalse((run_dir / "h2-map.json").exists())
        prompt = (capture / "h1-focused.json.prompt.txt").read_text(encoding="utf-8")
        self.assertNotIn("Soroban Core Security Model", prompt)

    def test_h2_receives_selected_knowledge(self) -> None:
        run_dir, capture, _ = self.run_scan("h2")
        self.assertTrue((run_dir / "h2-validated.json").is_file())
        self.assertFalse((run_dir / "h1-map.json").exists())
        prompt = (capture / "h2-focused.json.prompt.txt").read_text(encoding="utf-8")
        self.assertIn("Soroban Core Security Model", prompt)

    def test_both_modes_complete_and_manifest_has_no_secret(self) -> None:
        with patch.dict(os.environ, {"OPENROUTER_API_KEY": "must-not-appear"}):
            run_dir, _, _ = self.run_scan("both")
        manifest_text = (run_dir / "run-manifest.json").read_text(encoding="utf-8")
        manifest = json.loads(manifest_text)
        self.assertEqual(manifest["status"], "complete")
        self.assertEqual(set(manifest["findingCounts"]), {"h1", "h2"})
        self.assertNotIn("must-not-appear", manifest_text)
        self.assertFalse((run_dir / "hidden-ground-truth.json").exists())

    def test_resume_makes_no_additional_model_calls(self) -> None:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name)
        repository, revision = make_repository(root)
        invocation_log = root / "invocations.log"
        config = RunConfiguration.create(
            provider="codex-default", model="test-model", reasoning_effort="high"
        )
        arguments = dict(
            repository=repository,
            reference=revision,
            harness="h1",
            output_root=root / "runs",
            codex=str(FAKE_CODEX),
            config=config,
            additional_knowledge_dirs=[],
            retries=0,
            timeout_seconds=30,
            rate_limit_retries=0,
            rate_limit_cooldown_seconds=0,
        )
        with patch.dict(os.environ, {"FAKE_CODEX_INVOCATION_LOG": str(invocation_log)}):
            scan_repository(**arguments)
            first_count = len(invocation_log.read_text(encoding="utf-8").splitlines())
            scan_repository(**arguments)
            second_count = len(invocation_log.read_text(encoding="utf-8").splitlines())
        self.assertEqual(first_count, 4)
        self.assertEqual(second_count, first_count)


if __name__ == "__main__":
    unittest.main()
