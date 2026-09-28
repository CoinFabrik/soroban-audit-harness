#!/usr/bin/env python3
"""Offline stand-in for `codex exec` used by end-to-end tests."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path


def option(name: str) -> str:
    index = sys.argv.index(name)
    return sys.argv[index + 1]


output = Path(option("--output-last-message"))
prompt = sys.stdin.read()

capture_dir = os.environ.get("FAKE_CODEX_CAPTURE_DIR")
if capture_dir:
    path = Path(capture_dir)
    path.mkdir(parents=True, exist_ok=True)
    (path / f"{output.name}.prompt.txt").write_text(prompt, encoding="utf-8")

invocation_log = os.environ.get("FAKE_CODEX_INVOCATION_LOG")
if invocation_log:
    with Path(invocation_log).open("a", encoding="utf-8") as handle:
        handle.write(output.name + "\n")

if output.name.endswith("-baseline.json") or output.name.endswith("-focused.json"):
    payload = {
        "findings": [],
        "resolvedQuestions": ["Offline fixture response"],
        "fullyReviewedFiles": ["src/lib.rs"],
    }
elif output.name == "h1-map.json":
    payload = {
        "repositorySummary": "Minimal fixture",
        "contracts": [
            {"name": "Counter", "purpose": "Test fixture", "paths": ["src/lib.rs"]}
        ],
        "entryPoints": [],
        "stateAssets": ["Counter value"],
        "trustBoundaries": ["Public caller"],
        "invariants": ["Counter increases by one"],
        "investigationPackets": [],
        "coverage": ["src/lib.rs"],
    }
elif output.name == "h2-map.json":
    payload = {
        "repositorySummary": "Minimal fixture",
        "contracts": [
            {"name": "Counter", "purpose": "Test fixture", "paths": ["src/lib.rs"]}
        ],
        "entryPoints": [],
        "stateAssets": ["Counter value"],
        "trustBoundaries": ["Public caller"],
        "invariants": ["Counter increases by one"],
        "investigationPackets": [],
        "selectedKnowledgePackets": [
            {
                "id": "soroban-core",
                "rationale": "Soroban contract",
                "paths": ["src/lib.rs"],
            }
        ],
        "coverage": ["src/lib.rs"],
    }
elif output.name.endswith("-validated.json"):
    payload = {
        "validatedFindings": [],
        "rejectedCandidates": [],
        "fullyReviewedFiles": ["src/lib.rs"],
    }
else:
    raise SystemExit(f"Unexpected output path: {output}")

output.parent.mkdir(parents=True, exist_ok=True)
output.write_text(json.dumps(payload), encoding="utf-8")
print(json.dumps({"type": "turn.completed", "output": output.name}))
