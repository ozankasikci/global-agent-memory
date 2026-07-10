from __future__ import annotations

import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CONTRACT_ROOT = ROOT / "contracts" / "mcp" / "v1"

REQUIRED_TOOLS = {
    "memory_search",
    "memory_context",
    "memory_get",
    "memory_remember",
    "memory_update",
    "memory_approve",
    "memory_reject",
    "memory_supersede",
    "memory_archive",
    "memory_status",
    "memory_reindex",
    "memory_open",
    "memory_projects",
    "memory_tags",
}
REQUIRED_RESOURCES = {
    "memory://v1/status",
    "memory://v1/projects",
    "memory://v1/project/{project}",
    "memory://v1/project/{project}/recent",
    "memory://v1/project/{project}/decisions",
    "memory://v1/project/{project}/open-problems",
    "memory://v1/note/{id}",
    "memory://v1/candidates",
    "memory://v1/recent",
    "memory://v1/tags",
}
REQUIRED_PROMPTS = {
    "prepare_project_context",
    "summarize_project_state",
    "review_recent_decisions",
    "investigate_previous_bug",
    "prepare_implementation_handoff",
    "review_memory_candidates",
}


class ContractFilesTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.discovery = json.loads((CONTRACT_ROOT / "discovery.json").read_text())

    def test_contract_version_is_frozen_at_v1(self) -> None:
        self.assertEqual(self.discovery["contract_version"], 1)
        self.assertEqual(self.discovery["stability"], "frozen")

    def test_every_mandatory_capability_is_discoverable(self) -> None:
        self.assertEqual({item["name"] for item in self.discovery["tools"]}, REQUIRED_TOOLS)
        self.assertEqual({item["uriTemplate"] for item in self.discovery["resources"]}, REQUIRED_RESOURCES)
        self.assertEqual({item["name"] for item in self.discovery["prompts"]}, REQUIRED_PROMPTS)

    def test_names_are_unique_and_descriptions_are_actionable(self) -> None:
        for category, key in (("tools", "name"), ("resources", "uriTemplate"), ("prompts", "name")):
            values = [item[key] for item in self.discovery[category]]
            self.assertEqual(len(values), len(set(values)))
            for item in self.discovery[category]:
                self.assertGreaterEqual(len(item["description"]), 24)

    def test_tool_schemas_are_closed_and_return_common_envelopes(self) -> None:
        for tool in self.discovery["tools"]:
            schema = tool["inputSchema"]
            self.assertEqual(schema["type"], "object")
            self.assertFalse(schema["additionalProperties"])
            self.assertEqual(tool["outputSchema"]["$ref"], "schemas/success-envelope.json")

    def test_mutations_require_request_ids(self) -> None:
        mutation_names = {
            "memory_remember",
            "memory_update",
            "memory_approve",
            "memory_reject",
            "memory_supersede",
            "memory_archive",
            "memory_reindex",
        }
        for tool in self.discovery["tools"]:
            if tool["name"] in mutation_names:
                self.assertIn("request_id", tool["inputSchema"]["required"])

    def test_examples_are_partitioned_into_valid_and_invalid(self) -> None:
        examples = json.loads((CONTRACT_ROOT / "examples" / "calls.json").read_text())
        self.assertTrue(examples["valid"])
        self.assertTrue(examples["invalid"])
        self.assertTrue(all("reason" in item for item in examples["invalid"]))

    def test_generated_capability_files_match_discovery(self) -> None:
        for category, key in (("tools", "name"), ("resources", "name"), ("prompts", "name")):
            for item in self.discovery[category]:
                path = CONTRACT_ROOT / category / f"{item[key]}.json"
                self.assertEqual(json.loads(path.read_text()), item)


if __name__ == "__main__":
    unittest.main()
