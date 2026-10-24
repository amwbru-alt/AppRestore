from __future__ import annotations

import unittest

from apprevive_core.cli import _parse_selection
from apprevive_core.service import AppReviveError


class SelectionTests(unittest.TestCase):
    def test_valid_selection_and_deduplication(self) -> None:
        self.assertEqual(_parse_selection("1, 3-5, 3", 5), [0, 2, 3, 4])
        self.assertEqual(_parse_selection("08,09", 9), [7, 8])
        self.assertEqual(_parse_selection("ALL", 3), [0, 1, 2])
        self.assertEqual(_parse_selection("", 3), [])

    def test_invalid_selection_is_rejected_as_a_whole(self) -> None:
        invalid = [
            "0",
            "-1",
            "1,,2",
            "1,a,3",
            "1-",
            "5-2",
            "1-999999999",
            "4",
            "all,2",
            "١",
        ]
        for value in invalid:
            with self.subTest(value=value), self.assertRaises(AppReviveError):
                _parse_selection(value, 3)


if __name__ == "__main__":
    unittest.main()
