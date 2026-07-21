from __future__ import annotations

from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


class CandidateMemoryPromptScopeTests(unittest.TestCase):
    def test_decision_layers_do_not_promote_input_content(self) -> None:
        sources = [
            ROOT / "baml_src/ns_task/routing/flow.baml",
            ROOT / "baml_src/ns_memory/search/terms.baml",
            ROOT / "baml_src/ns_memory/search/depth.baml",
            ROOT / "baml_src/ns_memory/selection/flow.baml",
            ROOT / "baml_src/ns_task/prompting/flow.baml",
        ]

        for source_path in sources:
            source = source_path.read_text(encoding="utf-8")
            with self.subTest(source=source_path.name):
                self.assertIn("candidate_memory belongs only to the behavior", source)
                self.assertIn("Never copy, paraphrase", source)
                self.assertIn("infer", source)
                self.assertIn("promote their contents", source)
                self.assertIn("formatting preference", source)
                self.assertIn("Otherwise return", source)
                self.assertIn("null.", source)
                self.assertIn("instead", source)
                self.assertIn("return null", source)

    def test_candidate_reviewer_rejects_misplaced_content(self) -> None:
        source = (
            ROOT / "baml_src/ns_memory/candidate_review_prompt.baml"
        ).read_text(encoding="utf-8")

        self.assertIn("lesson about the decision behavior", source)
        self.assertIn("Reject candidates that store, paraphrase", source)
        self.assertIn("Do not rescue or reinterpret", source)
        self.assertIn("remember about the user or task", source)


if __name__ == "__main__":
    unittest.main()
