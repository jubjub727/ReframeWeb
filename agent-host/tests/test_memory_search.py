import unittest

from reframe_memory.search import (
    MemoryNodeSearch,
    StringSearch,
    TagSearch,
    build_memory_node_where,
)


class MemorySearchTests(unittest.TestCase):
    def test_tag_search_keeps_any_all_and_none_separate(self):
        parts = build_memory_node_where(
            MemoryNodeSearch(
                tags=TagSearch.build(
                    any_of=("preference", "workflow"),
                    all_of=("session",),
                    none_of=("stale",),
                )
            )
        )

        self.assertEqual(parts.variables["tag_any_of"], ["preference", "workflow"])
        self.assertEqual(parts.variables["tag_all_of"], ["session"])
        self.assertEqual(parts.variables["tag_none_of"], ["stale"])
        self.assertIn("array::intersect(tags, $tag_any_of)", parts.where_sql)
        self.assertIn("array::intersect(tags, $tag_all_of)", parts.where_sql)
        self.assertIn("array::intersect(tags, $tag_none_of)", parts.where_sql)

    def test_string_search_matches_any_declared_content_field(self):
        parts = build_memory_node_where(
            MemoryNodeSearch(
                strings=StringSearch.build(
                    contains=(" Scroll Speed ",),
                    equals=("Always Show Compact View",),
                ),
                string_fields=("title", "description", "title"),
            )
        )

        self.assertEqual(parts.variables["string_contains_0_0"], "scroll speed")
        self.assertEqual(parts.variables["string_contains_1_0"], "scroll speed")
        self.assertEqual(parts.variables["string_equals_0_0"], "Always Show Compact View")
        self.assertEqual(parts.variables["string_equals_1_0"], "Always Show Compact View")
        self.assertIn(
            "string::contains(string::lowercase(<string>content.title), $string_contains_0_0)",
            parts.where_sql,
        )
        self.assertIn(
            "string::contains(string::lowercase(<string>content.description), $string_contains_1_0)",
            parts.where_sql,
        )
        self.assertIn("content.title = $string_equals_0_0", parts.where_sql)
        self.assertIn("content.description = $string_equals_1_0", parts.where_sql)
        self.assertEqual(parts.where_sql.count(" OR "), 3)

    def test_string_search_requires_declared_content_fields(self):
        with self.assertRaisesRegex(ValueError, "requires at least one"):
            build_memory_node_where(
                MemoryNodeSearch(
                    strings=StringSearch.build(contains=("compact view",)),
                )
            )

    def test_string_search_rejects_invalid_content_fields(self):
        with self.assertRaisesRegex(ValueError, "invalid content field path"):
            build_memory_node_where(
                MemoryNodeSearch(
                    strings=StringSearch.build(contains=("compact view",)),
                    string_fields=("title; DELETE memory_node",),
                )
            )


if __name__ == "__main__":
    unittest.main()
