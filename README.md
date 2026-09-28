# Soroban Audit Harness

Soroban Audit Harness runs two complementary AI-assisted security-analysis workflows against a local Soroban repository.

- H1 is repository first. It generates and investigates security hypotheses using only the selected source snapshot.
- H2 is knowledge guided. It analyzes the same snapshot with a compact set of generalized security-review procedures.
- `both` runs H1 and H2 independently and keeps their artifacts separate.

The tool reports candidate findings, not confirmed vulnerabilities. Every result requires professional review before disclosure or publication.

## What H1 and H2 can see

Both harnesses receive the repository source at the selected Git revision, the selected model configuration, and their prompt and schema contracts.

H1 receives no audit report, known-vulnerability list, hidden ground truth, or H2 knowledge packet.

H2 receives the five generalized procedures in `soroban_audit/knowledge/default-v1`. It does not receive the evaluated project's report or known findings. The default pack was distilled from a larger research dataset of normalized audit findings, but the reports, private dataset, project-specific findings, and answer keys are not included in this repository.

Ordinary scans stop after candidate validation. Benchmark comparison against a separately reviewed audit dataset is intentionally outside the scan command.

## Requirements

- Python 3.11 or newer
- Git when analyzing a specific revision
- A current Codex CLI or Codex desktop CLI executable
- Provider credentials when required by the selected provider

## Installation

```sh
python3 -m venv .venv
. .venv/bin/activate
python3 -m pip install -e .
```

## Inspect a configuration without a model call

```sh
soroban-audit scan /path/to/repository \
  --harness both \
  --provider openrouter \
  --model vendor/model-name \
  --reasoning-effort high \
  --print-configuration
```

## Run H1

```sh
soroban-audit scan /path/to/repository \
  --ref <commit> \
  --harness h1 \
  --provider codex-default \
  --model gpt-5.6-sol \
  --reasoning-effort high
```

## Run H2 through OpenRouter

Store the API key in the environment without a `Bearer ` prefix:

```sh
export OPENROUTER_API_KEY="your-key"

soroban-audit scan /path/to/repository \
  --ref <commit> \
  --harness h2 \
  --provider openrouter \
  --model vendor/model-name \
  --reasoning-effort high
```

## Run both harnesses

```sh
soroban-audit scan /path/to/repository \
  --harness both \
  --provider openrouter \
  --model vendor/model-name
```

The output identity includes the provider, model, reasoning level, repository, revision, and selected harness mode. A run will not resume artifacts belonging to a different model configuration.

## Additional H2 knowledge

Additional private knowledge packets may be supplied without placing reports in this repository:

```sh
soroban-audit scan /path/to/repository \
  --harness h2 \
  --knowledge-dir /path/to/private/packets
```

The directory must contain a `catalog.json` and one Markdown file per packet ID. Packet IDs must not duplicate an ID in the default pack.

## Safety

The scanner materializes an isolated source snapshot and runs Codex with automatic approval review in its workspace-write sandbox. It does not change the user's working tree. Generated results may include false positives, duplicates, informational observations, or unsupported assumptions.

The tool never publishes findings or contacts maintainers. Keep findings about active projects private until they have been reviewed and responsibly disclosed.

## Tests

```sh
python3 -m unittest discover -s tests -v
```

The test suite uses a fake Codex executable for offline end-to-end coverage. GitHub Actions does not require API keys and does not make paid model calls.
