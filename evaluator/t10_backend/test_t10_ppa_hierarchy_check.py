"""Unit checks for the name-independent T10 physical hierarchy contract."""

import unittest

from t10_ppa_hierarchy_check import hierarchy_contract
from t10_structure_check import TOP


def design(tile_count: int = 16, pe_count: int = 16) -> dict:
    return {"modules": {
        TOP: {"cells": {
            f"tile_{index}": {"type": "renamed_tile"}
            for index in range(tile_count)
        }},
        "renamed_tile": {"cells": {
            **{f"pe_{index}": {"type": "renamed_pe"}
               for index in range(pe_count)},
            "bank": {"type": "renamed_bank"},
        }},
        "renamed_pe": {"cells": {}},
        "renamed_bank": {"cells": {}},
    }}


class T10PpaHierarchyCheckTest(unittest.TestCase):
    def test_renamed_hierarchy_passes(self) -> None:
        result = hierarchy_contract(design(), "renamed_pe")
        self.assertTrue(result["passed"], result)
        self.assertEqual(result["pe_instances_total"], 256)

    def test_wrong_tile_count_fails(self) -> None:
        self.assertFalse(hierarchy_contract(design(tile_count=15),
                                            "renamed_pe")["passed"])

    def test_wrong_pe_count_fails(self) -> None:
        self.assertFalse(hierarchy_contract(design(pe_count=15),
                                            "renamed_pe")["passed"])


if __name__ == "__main__":
    unittest.main()
