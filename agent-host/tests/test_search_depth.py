import unittest

from reframe_agent_host.agent_flow.search_depth import default_search_domains
import baml_sdk as types


class SearchDepthTests(unittest.TestCase):
    def test_default_domains_are_self_descriptive(self):
        domains = default_search_domains()

        self.assertEqual(
            [domain.id for domain in domains],
            ["task_catalog", "past_conversation_context"],
        )
        self.assertEqual(domains[0].searches, "Task memory nodes only.")
        self.assertIn("Session nodes", domains[1].searches)
        self.assertIn("SessionMemory", domains[1].hydrates)

    def test_depth_decision_keeps_timestamps_per_domain_explicit(self):
        decision = types.SearchDepthDecision(
            depths={
                "task_catalog": types.SearchDepthTimestamps(
                    created_after="2026-01-01T00:00:00Z",
                    read_after="2026-01-01T00:00:00Z",
                    updated_after="2026-01-01T00:00:00Z",
                )
            },
            candidate_memory=None,
        )

        self.assertEqual(
            decision.model_dump(mode="json"),
            {
                "depths": {
                    "task_catalog": {
                        "created_after": "2026-01-01T00:00:00Z",
                        "read_after": "2026-01-01T00:00:00Z",
                        "updated_after": "2026-01-01T00:00:00Z",
                    }
                },
                "candidate_memory": None,
            },
        )


if __name__ == "__main__":
    unittest.main()
