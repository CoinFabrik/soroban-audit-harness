from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from soroban_audit.runner import (
    DEFAULT_KNOWLEDGE,
    load_packet_catalog,
    load_selected_packets,
)


class KnowledgePacketTests(unittest.TestCase):
    def threat_map(self, *packet_ids: str) -> dict:
        return {
            "selectedKnowledgePackets": [
                {"id": packet_id, "rationale": "test", "paths": ["src/lib.rs"]}
                for packet_id in packet_ids
            ]
        }

    def test_default_catalog_and_bodies_load(self) -> None:
        catalog, paths = load_packet_catalog([DEFAULT_KNOWLEDGE])
        self.assertEqual(len(catalog), 5)
        selected = load_selected_packets(
            self.threat_map("soroban-core", "numeric-safety"), catalog, paths
        )
        self.assertEqual([item["id"] for item in selected], ["soroban-core", "numeric-safety"])
        self.assertTrue(all(item["content"].startswith("# ") for item in selected))

    def test_mandatory_packet_cannot_be_omitted(self) -> None:
        catalog, paths = load_packet_catalog([DEFAULT_KNOWLEDGE])
        with self.assertRaisesRegex(RuntimeError, "omitted mandatory"):
            load_selected_packets(self.threat_map("numeric-safety"), catalog, paths)

    def test_additional_catalog_is_merged(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            additional = Path(temporary_directory)
            (additional / "catalog.json").write_text(
                json.dumps(
                    [
                        {
                            "id": "private-procedure",
                            "title": "Private procedure",
                            "alwaysInclude": False,
                            "selectWhen": "Repository evidence supports it.",
                        }
                    ]
                ),
                encoding="utf-8",
            )
            (additional / "private-procedure.md").write_text(
                "# Private Procedure\n\nReview the evidence.", encoding="utf-8"
            )
            catalog, paths = load_packet_catalog([DEFAULT_KNOWLEDGE, additional])
            self.assertEqual(len(catalog), 6)
            self.assertIn("private-procedure", paths)

    def test_duplicate_additional_id_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            additional = Path(temporary_directory)
            (additional / "catalog.json").write_text(
                json.dumps(
                    [
                        {
                            "id": "soroban-core",
                            "title": "Duplicate",
                            "alwaysInclude": False,
                            "selectWhen": "Never",
                        }
                    ]
                ),
                encoding="utf-8",
            )
            (additional / "soroban-core.md").write_text("# Duplicate", encoding="utf-8")
            with self.assertRaisesRegex(RuntimeError, "duplicated"):
                load_packet_catalog([DEFAULT_KNOWLEDGE, additional])


if __name__ == "__main__":
    unittest.main()
