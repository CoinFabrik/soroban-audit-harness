from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from soroban_audit.runner import SCHEMAS
from soroban_audit.schema_validation import (
    SchemaValidationError,
    load_and_validate_output,
    prompt_with_embedded_schema,
    validate_against_schema,
)


class SchemaValidationTests(unittest.TestCase):
    def test_valid_findings_artifact(self) -> None:
        validate_against_schema(
            {
                "findings": [],
                "resolvedQuestions": [],
                "fullyReviewedFiles": ["src/lib.rs"],
            },
            SCHEMAS / "findings.schema.json",
        )

    def test_missing_required_property_is_rejected(self) -> None:
        with self.assertRaisesRegex(SchemaValidationError, "missing required"):
            validate_against_schema(
                {"findings": []},
                SCHEMAS / "findings.schema.json",
            )

    def test_embedded_schema_names_required_properties(self) -> None:
        prompt = prompt_with_embedded_schema(
            "Audit this repository.", SCHEMAS / "findings.schema.json"
        )
        self.assertIn("Required final output contract", prompt)
        self.assertIn('"fullyReviewedFiles"', prompt)

    def test_numeric_string_repair_is_mechanical(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            output = root / "output.json"
            schema = root / "schema.json"
            output.write_text('{"startLine":"253}', encoding="utf-8")
            schema.write_text(
                json.dumps(
                    {
                        "type": "object",
                        "additionalProperties": False,
                        "required": ["startLine"],
                        "properties": {"startLine": {"type": "integer"}},
                    }
                ),
                encoding="utf-8",
            )
            value, repaired = load_and_validate_output(output, schema)
        self.assertTrue(repaired)
        self.assertEqual(value["startLine"], 253)


if __name__ == "__main__":
    unittest.main()
