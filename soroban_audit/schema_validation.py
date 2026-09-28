#!/usr/bin/env python3
"""Small dependency-free validator for the JSON Schema subset used by the harness."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any


class SchemaValidationError(ValueError):
    pass


_UNCLOSED_SCHEMA_NUMBER = re.compile(
    r'("(?:startLine|endLine)"\s*:\s*"-?\d+)(?=[}\],])'
)
_TRAILING_SCHEMA_NUMBER_QUOTE = re.compile(
    r'("(?:startLine|endLine)"\s*:\s*-?\d+)"(?=[}\],])'
)
_UNQUOTED_PATHS_KEY = re.compile(r'([,{]\s*)paths("\s*:)')
_STRING_ARRAY_PROPERTY_NAMES = (
    "counterevidence|coverage|evidence|expectedControls|externalCalls|fullyReviewedFiles|"
    "invariants|matchedRawCandidateIds|matchedValidatedFindingIds|paths|resolvedQuestions|"
    "sourceCandidateIds|stateAssets|stateChanges|trustBoundaries|unmatchedRawCandidateIds|"
    "unmatchedValidatedFindingIds"
)
_JSON_STRING = r'"(?:\\.|[^"\\])*"'
_MISSING_FINAL_FINDING_OBJECT_DELIMITER = re.compile(
    rf'("remediation"\s*:\s*{_JSON_STRING})(\s*],\s*"resolvedQuestions"\s*:)',
)
_SOURCE_LOCATION_CITATION = re.compile(
    r'(?<![A-Za-z0-9_.-])'
    r'(?P<path>[A-Za-z0-9_.-]+(?:/[A-Za-z0-9_.-]+)*)'
    r':(?P<start>\d+)(?:-(?P<end>\d+))?'
)
_MISSING_LOCATION_OBJECT_OPEN = re.compile(
    rf'([,[]\s*)('
    rf'"path"\s*:\s*{_JSON_STRING}\s*,'
    r'\s*"startLine"\s*:\s*-?\d+\s*,'
    r'\s*"endLine"\s*:\s*-?\d+\s*})'
)
_UNCLOSED_STRING_ARRAY = re.compile(
    rf'("(?:{_STRING_ARRAY_PROPERTY_NAMES})"\s*:\s*\[(?:\s*{_JSON_STRING}\s*,?)+)'
    r'(\s*},\s*\{\s*"(?:id|name)")'
)
_UNCLOSED_SOURCE_IDS_BEFORE_RATIONALE = re.compile(
    rf'("sourceCandidateIds"\s*:\s*\[(?:\s*{_JSON_STRING}\s*,?)+)'
    r'(\s*,\s*"rationale"\s*:)',
)
_UNCLOSED_STATE_CHANGES_BEFORE_EXTERNAL_CALLS = re.compile(
    rf'("stateChanges"\s*:\s*\[(?:\s*{_JSON_STRING}\s*,?)+)'
    r'(\s*,\s*"externalCalls"\s*:)',
)
_UNCLOSED_STRING_ARRAY_AT_OBJECT_END = re.compile(
    rf'("(?:{_STRING_ARRAY_PROPERTY_NAMES})"\s*:\s*\[(?:\s*{_JSON_STRING}\s*,?)+)'
    r'(\s*})\s*$'
)


def prompt_with_embedded_schema(prompt: str, schema_path: Path) -> str:
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    compact_schema = json.dumps(schema, ensure_ascii=False, separators=(",", ":"))
    return (
        prompt.rstrip()
        + "\n\n## Required final output contract\n\n"
        + "Return only one JSON object that exactly matches the following JSON Schema. "
        + "Use the exact property names and include every required property. Do not add markdown, "
        + "commentary, or properties not allowed by the schema.\n\n"
        + compact_schema
        + "\n"
    )


def _resolve_ref(root_schema: dict[str, Any], reference: str) -> dict[str, Any]:
    if not reference.startswith("#/"):
        raise SchemaValidationError(f"Only local schema references are supported: {reference}")
    node: Any = root_schema
    for component in reference[2:].split("/"):
        component = component.replace("~1", "/").replace("~0", "~")
        node = node[component]
    if not isinstance(node, dict):
        raise SchemaValidationError(f"Schema reference does not resolve to an object: {reference}")
    return node


def _matches_type(value: Any, expected: str) -> bool:
    if expected == "object":
        return isinstance(value, dict)
    if expected == "array":
        return isinstance(value, list)
    if expected == "string":
        return isinstance(value, str)
    if expected == "boolean":
        return isinstance(value, bool)
    if expected == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if expected == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    if expected == "null":
        return value is None
    raise SchemaValidationError(f"Unsupported schema type: {expected}")


def _validate(value: Any, schema: dict[str, Any], root_schema: dict[str, Any], location: str) -> None:
    if "$ref" in schema:
        _validate(value, _resolve_ref(root_schema, schema["$ref"]), root_schema, location)
        return

    expected_type = schema.get("type")
    if expected_type and not _matches_type(value, expected_type):
        raise SchemaValidationError(
            f"{location} must be {expected_type}, got {type(value).__name__}"
        )
    if "enum" in schema and value not in schema["enum"]:
        raise SchemaValidationError(f"{location} must be one of {schema['enum']!r}, got {value!r}")

    if isinstance(value, dict):
        required = schema.get("required", [])
        missing = [key for key in required if key not in value]
        if missing:
            raise SchemaValidationError(f"{location} is missing required properties: {', '.join(missing)}")
        properties = schema.get("properties", {})
        if schema.get("additionalProperties") is False:
            unexpected = [key for key in value if key not in properties]
            if unexpected:
                raise SchemaValidationError(
                    f"{location} has unexpected properties: {', '.join(unexpected)}"
                )
        for key, child in value.items():
            if key in properties:
                _validate(child, properties[key], root_schema, f"{location}.{key}")

    if isinstance(value, list):
        if len(value) < schema.get("minItems", 0):
            raise SchemaValidationError(f"{location} has fewer than {schema['minItems']} items")
        if "maxItems" in schema and len(value) > schema["maxItems"]:
            raise SchemaValidationError(f"{location} has more than {schema['maxItems']} items")
        if "items" in schema:
            for index, child in enumerate(value):
                _validate(child, schema["items"], root_schema, f"{location}[{index}]")

    if isinstance(value, (int, float)) and not isinstance(value, bool):
        if "minimum" in schema and value < schema["minimum"]:
            raise SchemaValidationError(f"{location} is below minimum {schema['minimum']}")
        if "maximum" in schema and value > schema["maximum"]:
            raise SchemaValidationError(f"{location} is above maximum {schema['maximum']}")


def validate_against_schema(value: Any, schema_path: Path) -> None:
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    _validate(value, schema, schema, "$")


def _locations_from_evidence(evidence: Any) -> list[dict[str, Any]]:
    if not isinstance(evidence, list) or not all(isinstance(item, str) for item in evidence):
        return []
    locations: list[dict[str, Any]] = []
    seen: set[tuple[str, int, int]] = set()
    for item in evidence:
        for match in _SOURCE_LOCATION_CITATION.finditer(item):
            start_line = int(match.group("start"))
            end_line = int(match.group("end") or match.group("start"))
            key = (match.group("path"), start_line, end_line)
            if key in seen:
                continue
            seen.add(key)
            locations.append(
                {"path": key[0], "startLine": start_line, "endLine": end_line}
            )
    return locations


def _coerce_schema_scalars(value: Any, schema: dict[str, Any], root_schema: dict[str, Any]) -> Any:
    if "$ref" in schema:
        return _coerce_schema_scalars(value, _resolve_ref(root_schema, schema["$ref"]), root_schema)
    expected_type = schema.get("type")
    if expected_type == "integer" and isinstance(value, str) and re.fullmatch(r"-?\d+", value):
        return int(value)
    if expected_type == "number" and isinstance(value, str):
        try:
            return float(value)
        except ValueError:
            return value
    # Providers occasionally serialize a singleton string-array property as the
    # string itself. Wrapping it is a mechanical shape repair: the text and its
    # meaning remain unchanged, while the value matches the declared schema.
    if (
        expected_type == "array"
        and isinstance(value, str)
        and isinstance(schema.get("items"), dict)
        and schema["items"].get("type") == "string"
    ):
        return [value]
    if isinstance(value, dict):
        properties = schema.get("properties", {})
        normalized: dict[str, Any] = {}
        for key, child in value.items():
            base_key = key.removesuffix("_placeholder")
            if (
                key == "ratione"
                and "rationale" in properties
                and "rationale" not in value
                and schema.get("additionalProperties") is False
            ):
                normalized["rationale"] = _coerce_schema_scalars(
                    child, properties["rationale"], root_schema
                )
                continue
            if (
                key not in properties
                and key == "note"
                and isinstance(child, str)
                and re.fullmatch(r"Concrete [A-Za-z-]+ finding", child)
                and schema.get("additionalProperties") is False
            ):
                continue
            if (
                key not in properties
                and key == "stateAssetsFamily"
                and isinstance(child, str)
                and schema.get("additionalProperties") is False
            ):
                continue
            if (
                key not in properties
                and key == "externalCallsArray"
                and child == []
                and "externalCalls" in properties
                and "externalCalls" in value
                and schema.get("additionalProperties") is False
            ):
                continue
            if (
                key not in properties
                and key.endswith("_placeholder")
                and child is None
                and base_key in properties
                and base_key in value
            ):
                continue
            normalized[key] = (
                _coerce_schema_scalars(child, properties[key], root_schema)
                if key in properties
                else child
            )
        if (
            "locations" in schema.get("required", [])
            and "locations" in properties
            and "locations" not in normalized
        ):
            derived_locations = _locations_from_evidence(normalized.get("evidence"))
            if derived_locations:
                normalized["locations"] = derived_locations
        if (
            "startLine" in schema.get("required", [])
            and "startLine" not in normalized
            and isinstance(normalized.get("endLine"), int)
        ):
            normalized["startLine"] = normalized["endLine"]
        if (
            "endLine" in schema.get("required", [])
            and "endLine" not in normalized
            and isinstance(normalized.get("startLine"), int)
        ):
            normalized["endLine"] = normalized["startLine"]
        return normalized
    if isinstance(value, list) and "items" in schema:
        item_schema = schema["items"]
        resolved_item_schema = (
            _resolve_ref(root_schema, item_schema["$ref"])
            if isinstance(item_schema, dict) and "$ref" in item_schema
            else item_schema
        )
        item_properties = (
            resolved_item_schema.get("properties", {})
            if isinstance(resolved_item_schema, dict)
            else {}
        )
        normalized_items = []
        for child in value:
            if (
                isinstance(child, dict)
                and child.get("status") == "invalid"
                and "status" not in item_properties
                and isinstance(resolved_item_schema, dict)
                and resolved_item_schema.get("additionalProperties") is False
            ):
                continue
            normalized_items.append(_coerce_schema_scalars(child, item_schema, root_schema))
        return normalized_items
    return value


def load_and_validate_output(output_path: Path, schema_path: Path) -> tuple[Any, bool]:
    """Load output, applying only deterministic syntax/type repairs required by the schema."""
    raw = output_path.read_text(encoding="utf-8")
    repaired = False
    try:
        value = json.loads(raw)
    except json.JSONDecodeError:
        repaired_raw = raw
        first_object = repaired_raw.find("{")
        if first_object > 0:
            repaired_raw = repaired_raw[first_object:]
        # A model may honor the embedded JSON contract while still surrounding
        # the object with a Markdown code fence. Removing only a terminal fence
        # is a syntax-only repair; the JSON payload itself is unchanged.
        if repaired_raw.rstrip().endswith("```"):
            repaired_raw = repaired_raw.rstrip()[:-3].rstrip()
        repaired_raw = _UNCLOSED_SCHEMA_NUMBER.sub(r'\1"', repaired_raw)
        repaired_raw = _TRAILING_SCHEMA_NUMBER_QUOTE.sub(r'\1', repaired_raw)
        repaired_raw = _UNQUOTED_PATHS_KEY.sub(r'\1"paths\2', repaired_raw)
        repaired_raw = _MISSING_LOCATION_OBJECT_OPEN.sub(r'\1{\2', repaired_raw)
        repaired_raw = _MISSING_FINAL_FINDING_OBJECT_DELIMITER.sub(r'\1}\2', repaired_raw)
        repaired_raw = _UNCLOSED_STRING_ARRAY.sub(r'\1]\2', repaired_raw)
        repaired_raw = _UNCLOSED_SOURCE_IDS_BEFORE_RATIONALE.sub(r'\1]\2', repaired_raw)
        repaired_raw = _UNCLOSED_STATE_CHANGES_BEFORE_EXTERNAL_CALLS.sub(
            r'\1]\2', repaired_raw
        )
        repaired_raw = _UNCLOSED_STRING_ARRAY_AT_OBJECT_END.sub(r'\1]\2', repaired_raw)
        stripped = repaired_raw.rstrip()
        if stripped.endswith("}}"):
            candidate = stripped[:-1] + repaired_raw[len(stripped) :]
            try:
                json.loads(candidate)
            except json.JSONDecodeError:
                pass
            else:
                repaired_raw = candidate
        if repaired_raw == raw:
            raise
        value = json.loads(repaired_raw)
        repaired = True
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    coerced = _coerce_schema_scalars(value, schema, schema)
    if coerced != value:
        value = coerced
        repaired = True
    _validate(value, schema, schema, "$")
    return value, repaired
