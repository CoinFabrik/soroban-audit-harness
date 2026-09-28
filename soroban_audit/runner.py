"""Repository scanner shared by the H1 and H2 harness modes."""

from __future__ import annotations

import hashlib
import io
import json
import os
import shutil
import subprocess
import tarfile
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .provider_config import RunConfiguration, safe_component, validate_manifest_identity
from .schema_validation import (
    SchemaValidationError,
    load_and_validate_output,
    prompt_with_embedded_schema,
)


PACKAGE_ROOT = Path(__file__).resolve().parent
PROMPTS = PACKAGE_ROOT / "prompts"
SCHEMAS = PACKAGE_ROOT / "schemas"
DEFAULT_KNOWLEDGE = PACKAGE_ROOT / "knowledge" / "default-v1"
HARNESS_MODES = ("h1", "h2", "both")


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def render_prompt(path: Path, replacements: dict[str, Any] | None = None) -> str:
    prompt = path.read_text(encoding="utf-8")
    for key, value in (replacements or {}).items():
        prompt = prompt.replace(
            "{{" + key + "}}",
            json.dumps(value, ensure_ascii=False, indent=2),
        )
    return prompt


def is_rate_limited(result: subprocess.CompletedProcess[str]) -> bool:
    combined = f"{result.stdout or ''}\n{result.stderr or ''}"
    return "429 Too Many Requests" in combined


def build_stage_command(
    *,
    codex: str,
    config: RunConfiguration,
    workdir: Path,
    schema: Path,
    output: Path,
) -> list[str]:
    command = [*config.codex_exec_prefix(codex), "--json"]
    if config.provider != "openrouter":
        command.extend(["--output-schema", str(schema)])
    command.extend(
        [
            "--output-last-message",
            str(output),
            "--cd",
            str(workdir),
            "-",
        ]
    )
    return command


def run_stage(
    *,
    codex: str,
    config: RunConfiguration,
    stage: str,
    workdir: Path,
    prompt: str,
    schema: Path,
    output: Path,
    logs: Path,
    retries: int,
    timeout_seconds: int,
    rate_limit_retries: int,
    rate_limit_cooldown_seconds: int,
) -> dict[str, Any]:
    if output.exists():
        parsed, repaired = load_and_validate_output(output, schema)
        if repaired:
            write_json(output, parsed)
        print(f"resuming: {stage}", flush=True)
        return parsed

    effective_prompt = (
        prompt_with_embedded_schema(prompt, schema)
        if config.provider == "openrouter"
        else prompt
    )
    command = build_stage_command(
        codex=codex,
        config=config,
        workdir=workdir,
        schema=schema,
        output=output,
    )
    logs.mkdir(parents=True, exist_ok=True)
    ordinary_failures = 0
    rate_limit_failures = 0
    attempt = 0
    while True:
        attempt += 1
        print(f"starting: {stage} attempt={attempt}", flush=True)
        try:
            result = subprocess.run(
                command,
                input=effective_prompt,
                text=True,
                capture_output=True,
                env={**os.environ, "GIT_TERMINAL_PROMPT": "0"},
                timeout=timeout_seconds,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            stdout = exc.stdout.decode() if isinstance(exc.stdout, bytes) else (exc.stdout or "")
            stderr = exc.stderr.decode() if isinstance(exc.stderr, bytes) else (exc.stderr or "")
            result = subprocess.CompletedProcess(command, 124, stdout, stderr)

        suffix = f".attempt-{attempt}"
        (logs / f"{stage}{suffix}.events.jsonl").write_text(
            result.stdout or "", encoding="utf-8"
        )
        (logs / f"{stage}{suffix}.stderr.log").write_text(
            result.stderr or "", encoding="utf-8"
        )
        if result.returncode == 0 and output.exists():
            try:
                parsed, repaired = load_and_validate_output(output, schema)
            except (json.JSONDecodeError, SchemaValidationError, TypeError) as exc:
                with (logs / f"{stage}{suffix}.stderr.log").open(
                    "a", encoding="utf-8"
                ) as handle:
                    handle.write(f"\nHarness output validation failed: {exc}\n")
            else:
                if repaired:
                    write_json(output, parsed)
                print(f"completed: {stage}", flush=True)
                return parsed

        output.unlink(missing_ok=True)
        if is_rate_limited(result) and rate_limit_failures < rate_limit_retries:
            rate_limit_failures += 1
            remaining = rate_limit_cooldown_seconds
            while remaining > 0:
                interval = min(60, remaining)
                print(
                    f"rate-limit cooldown: stage={stage} "
                    f"retry={rate_limit_failures} remaining={remaining}s",
                    flush=True,
                )
                time.sleep(interval)
                remaining -= interval
            continue
        ordinary_failures += 1
        if ordinary_failures > retries:
            break
    raise RuntimeError(f"Stage {stage} failed after {attempt} attempts")


def load_packet_catalog(knowledge_dirs: list[Path]) -> tuple[list[dict[str, Any]], dict[str, Path]]:
    catalog: list[dict[str, Any]] = []
    packet_paths: dict[str, Path] = {}
    for directory in knowledge_dirs:
        resolved = directory.expanduser().resolve()
        catalog_path = resolved / "catalog.json"
        if not catalog_path.is_file():
            raise RuntimeError(f"Knowledge catalog is missing: {catalog_path}")
        entries = read_json(catalog_path)
        if not isinstance(entries, list):
            raise RuntimeError(f"Knowledge catalog must contain an array: {catalog_path}")
        for entry in entries:
            packet_id = entry.get("id") if isinstance(entry, dict) else None
            if not isinstance(packet_id, str) or not packet_id:
                raise RuntimeError(f"Invalid packet entry in {catalog_path}")
            if packet_id in packet_paths:
                raise RuntimeError(f"Knowledge packet ID is duplicated: {packet_id}")
            packet_path = resolved / f"{packet_id}.md"
            if not packet_path.is_file():
                raise RuntimeError(f"Knowledge packet body is missing: {packet_path}")
            packet_paths[packet_id] = packet_path
            catalog.append(entry)
    return catalog, packet_paths


def load_selected_packets(
    threat_map: dict[str, Any],
    catalog: list[dict[str, Any]],
    packet_paths: dict[str, Path],
) -> list[dict[str, str]]:
    catalog_by_id = {item["id"]: item for item in catalog}
    selected_ids = [item["id"] for item in threat_map["selectedKnowledgePackets"]]
    if len(selected_ids) != len(set(selected_ids)):
        raise RuntimeError("Threat map selected a knowledge packet more than once")
    mandatory_ids = {item["id"] for item in catalog if item.get("alwaysInclude")}
    if not mandatory_ids.issubset(selected_ids):
        missing = ", ".join(sorted(mandatory_ids - set(selected_ids)))
        raise RuntimeError(f"Threat map omitted mandatory knowledge packets: {missing}")
    unknown = [packet_id for packet_id in selected_ids if packet_id not in catalog_by_id]
    if unknown:
        raise RuntimeError(f"Threat map selected unknown knowledge packets: {', '.join(unknown)}")
    return [
        {
            "id": packet_id,
            "title": catalog_by_id[packet_id]["title"],
            "content": packet_paths[packet_id].read_text(encoding="utf-8"),
        }
        for packet_id in selected_ids
    ]


def _safe_extract_tar(data: bytes, destination: Path) -> None:
    destination.mkdir(parents=True, exist_ok=False)
    root = destination.resolve()
    with tarfile.open(fileobj=io.BytesIO(data), mode="r:") as archive:
        for member in archive.getmembers():
            target = (destination / member.name).resolve()
            if target != root and root not in target.parents:
                raise RuntimeError(f"Unsafe archive member: {member.name}")
        archive.extractall(destination, filter="data")


def _git(repository: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(repository), *args],
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def resolve_repository(repository: Path, reference: str | None) -> tuple[str, str]:
    repository = repository.expanduser().resolve()
    if not repository.is_dir():
        raise RuntimeError(f"Repository directory does not exist: {repository}")
    try:
        revision = _git(repository, "rev-parse", "--verify", f"{reference or 'HEAD'}^{{commit}}")
    except (subprocess.CalledProcessError, FileNotFoundError):
        if reference:
            raise RuntimeError("--ref requires a Git repository and a resolvable revision")
        digest = hashlib.sha256()
        for path in sorted(repository.rglob("*")):
            if not path.is_file() or ".git" in path.parts:
                continue
            digest.update(str(path.relative_to(repository)).encode())
            digest.update(path.read_bytes())
        revision = f"working-tree-{digest.hexdigest()[:16]}"
    return safe_component(repository.name), revision


def materialize_snapshot(repository: Path, revision: str, destination: Path) -> None:
    repository = repository.expanduser().resolve()
    if destination.exists():
        return
    if not revision.startswith("working-tree-"):
        archive = subprocess.run(
            ["git", "-C", str(repository), "archive", "--format=tar", revision],
            check=True,
            capture_output=True,
        )
        _safe_extract_tar(archive.stdout, destination)
    else:
        shutil.copytree(
            repository,
            destination,
            ignore=shutil.ignore_patterns(".git", "target", "soroban-audit-runs", "__pycache__"),
        )


def condition_run(
    *,
    condition: str,
    source: Path,
    run_dir: Path,
    codex: str,
    config: RunConfiguration,
    knowledge_dirs: list[Path],
    retries: int,
    timeout_seconds: int,
    rate_limit_retries: int,
    rate_limit_cooldown_seconds: int,
) -> dict[str, Any]:
    stage_options = {
        "codex": codex,
        "config": config,
        "workdir": source,
        "logs": run_dir / "logs",
        "retries": retries,
        "timeout_seconds": timeout_seconds,
        "rate_limit_retries": rate_limit_retries,
        "rate_limit_cooldown_seconds": rate_limit_cooldown_seconds,
    }
    baseline = run_stage(
        **stage_options,
        stage=f"{condition}-baseline",
        prompt=render_prompt(PROMPTS / "02-baseline-audit.md"),
        schema=SCHEMAS / "findings.schema.json",
        output=run_dir / f"{condition}-baseline.json",
    )

    selected_packets: list[dict[str, str]] = []
    if condition == "h1":
        threat_map = run_stage(
            **stage_options,
            stage="h1-map",
            prompt=render_prompt(PROMPTS / "h1" / "01-map-contract.md"),
            schema=SCHEMAS / "h1-threat-map.schema.json",
            output=run_dir / "h1-map.json",
        )
        focused_prompt = render_prompt(
            PROMPTS / "h1" / "03-focused-investigation.md",
            {"THREAT_MAP_JSON": threat_map},
        )
    else:
        catalog, packet_paths = load_packet_catalog(knowledge_dirs)
        threat_map = run_stage(
            **stage_options,
            stage="h2-map",
            prompt=render_prompt(
                PROMPTS / "01-map-contract.md",
                {"CYBER_PACKET_CATALOG_JSON": catalog},
            ),
            schema=SCHEMAS / "threat-map.schema.json",
            output=run_dir / "h2-map.json",
        )
        selected_packets = load_selected_packets(threat_map, catalog, packet_paths)
        focused_prompt = render_prompt(
            PROMPTS / "03-focused-investigation.md",
            {
                "THREAT_MAP_JSON": threat_map,
                "CYBER_KNOWLEDGE_PACKETS_JSON": selected_packets,
            },
        )

    if not (threat_map.get("contracts") or threat_map.get("entryPoints")):
        raise RuntimeError(f"{condition} map did not establish minimum source coverage")
    focused = run_stage(
        **stage_options,
        stage=f"{condition}-focused",
        prompt=focused_prompt,
        schema=SCHEMAS / "findings.schema.json",
        output=run_dir / f"{condition}-focused.json",
    )
    validated = run_stage(
        **stage_options,
        stage=f"{condition}-validate",
        prompt=render_prompt(
            PROMPTS / "04-validate-findings.md",
            {
                "BASELINE_CANDIDATES_JSON": baseline,
                "FOCUSED_CANDIDATES_JSON": focused,
            },
        ),
        schema=SCHEMAS / "validation.schema.json",
        output=run_dir / f"{condition}-validated.json",
    )
    if not baseline.get("fullyReviewedFiles"):
        raise RuntimeError(f"{condition} baseline did not establish minimum source coverage")
    return {
        "map": threat_map,
        "baseline": baseline,
        "focused": focused,
        "validated": validated,
        "selectedPackets": selected_packets,
    }


def write_summary(run_dir: Path, condition: str, validated: dict[str, Any]) -> None:
    findings = validated.get("validatedFindings", [])
    lines = [
        f"# {condition.upper()} Candidate Findings",
        "",
        "These findings were generated by an AI-assisted review and are not confirmed vulnerabilities.",
        "They require professional validation before disclosure or publication.",
        "",
        f"Validated candidate count: {len(findings)}",
        "",
    ]
    for finding in findings:
        lines.extend(
            [
                f"## {finding['id']} {finding['title']}",
                "",
                f"- Severity: {finding['severity']}",
                f"- Confidence: {finding['confidence']}",
                f"- Disposition: {finding['disposition']}",
                f"- Category: {finding['category']}",
                "",
                finding["validationRationale"],
                "",
            ]
        )
    (run_dir / f"{condition}-results.md").write_text("\n".join(lines), encoding="utf-8")


def scan_repository(
    *,
    repository: Path,
    reference: str | None,
    harness: str,
    output_root: Path,
    codex: str,
    config: RunConfiguration,
    additional_knowledge_dirs: list[Path],
    retries: int,
    timeout_seconds: int,
    rate_limit_retries: int,
    rate_limit_cooldown_seconds: int,
) -> Path:
    if harness not in HARNESS_MODES:
        raise ValueError(f"Unsupported harness mode: {harness}")
    repository = repository.expanduser().resolve()
    repository_name, revision = resolve_repository(repository, reference)
    run_dir = (
        config.run_root(output_root.expanduser().resolve())
        / repository_name
        / safe_component(revision)
        / harness
    )
    run_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = run_dir / "run-manifest.json"
    if manifest_path.exists():
        manifest = read_json(manifest_path)
        validate_manifest_identity(manifest, config)
        if manifest.get("repositoryRevision") != revision or manifest.get("harness") != harness:
            raise RuntimeError("Existing run manifest belongs to a different scan")
    else:
        prompt_paths = [
            PROMPTS / "02-baseline-audit.md",
            PROMPTS / "04-validate-findings.md",
            PROMPTS / "h1" / "01-map-contract.md",
            PROMPTS / "h1" / "03-focused-investigation.md",
            PROMPTS / "01-map-contract.md",
            PROMPTS / "03-focused-investigation.md",
        ]
        manifest = {
            **config.identity(),
            "repositoryName": repository_name,
            "repositoryRevision": revision,
            "harness": harness,
            "status": "in-progress",
            "startedAt": datetime.now(timezone.utc).isoformat(),
            "sourceSnapshotIsolated": True,
            "auditReportsVisibleToDiscovery": False,
            "groundTruthVisibleToDiscovery": False,
            "promptHashes": {
                str(path.relative_to(PACKAGE_ROOT)): sha256(path) for path in prompt_paths
            },
        }
    manifest["status"] = "in-progress"
    write_json(manifest_path, manifest)

    snapshot = run_dir / "snapshot"
    materialize_snapshot(repository, revision, snapshot)
    knowledge_dirs = [DEFAULT_KNOWLEDGE, *additional_knowledge_dirs]
    conditions = ("h1", "h2") if harness == "both" else (harness,)
    try:
        results: dict[str, dict[str, Any]] = {}
        for condition in conditions:
            results[condition] = condition_run(
                condition=condition,
                source=snapshot,
                run_dir=run_dir,
                codex=codex,
                config=config,
                knowledge_dirs=knowledge_dirs,
                retries=retries,
                timeout_seconds=timeout_seconds,
                rate_limit_retries=rate_limit_retries,
                rate_limit_cooldown_seconds=rate_limit_cooldown_seconds,
            )
            write_summary(run_dir, condition, results[condition]["validated"])
        manifest["status"] = "complete"
        manifest["completedAt"] = datetime.now(timezone.utc).isoformat()
        manifest["findingCounts"] = {
            condition: len(result["validated"].get("validatedFindings", []))
            for condition, result in results.items()
        }
        if "h2" in results:
            manifest["h2KnowledgePackets"] = [
                {
                    "id": item["id"],
                    "contentSha256": hashlib.sha256(item["content"].encode()).hexdigest(),
                }
                for item in results["h2"]["selectedPackets"]
            ]
        write_json(manifest_path, manifest)
    except Exception as exc:
        manifest["status"] = "failed"
        manifest["failedAt"] = datetime.now(timezone.utc).isoformat()
        manifest["failure"] = f"{type(exc).__name__}: {exc}"
        write_json(manifest_path, manifest)
        raise
    return run_dir
