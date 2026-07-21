from __future__ import annotations

import re
import unittest

from tests.completion_equation_cases import ALL_EQUATION_CASES, USER_TRANSCRIPT_CASES

REQUEST = re.compile(
    r"what is (?P<base>\d+) to the power of (?P<exponent>\d+)"
    r"(?: (?P<operation>plus|minus) (?P<adjustment>\d+))?"
)


def _number(value: str) -> int:
    return int(value.replace(",", ""))


class CompletionEquationCorpusTests(unittest.TestCase):
    def test_corpus_has_25_independently_correct_equations(self) -> None:
        self.assertEqual(len(ALL_EQUATION_CASES), 25)
        self.assertEqual(len({case.request for case in ALL_EQUATION_CASES}), 25)
        self.assertEqual(len(USER_TRANSCRIPT_CASES), 6)

        for case in ALL_EQUATION_CASES:
            with self.subTest(request=case.request):
                request = REQUEST.fullmatch(case.request)
                self.assertIsNotNone(request)
                assert request is not None
                expected = int(request["base"]) ** int(request["exponent"])
                adjustment = int(request["adjustment"] or 0)
                if request["operation"] == "plus":
                    expected += adjustment
                elif request["operation"] == "minus":
                    expected -= adjustment

                reference = _number(case.reference)
                alternatives = [_number(value) for value in case.alternatives]
                self.assertEqual(reference, expected)
                self.assertEqual(abs(alternatives[0] - reference), 1)
                self.assertEqual(len(set(alternatives)), 3)
                self.assertNotIn(reference, alternatives)

    def test_live_suite_checks_four_candidates_per_equation(self) -> None:
        for case in ALL_EQUATION_CASES:
            with self.subTest(request=case.request):
                self.assertEqual(len(case.candidates), 4)
                self.assertEqual(case.candidates[0], case.reference)
                self.assertEqual(case.candidates[1:], case.alternatives)


if __name__ == "__main__":
    unittest.main()
