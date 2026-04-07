"""Integration coverage for the preserved deterministic Excel parser."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import openpyxl

from src.excel_parser import ExcelOrderParser


class ExcelParserIntegrationTests(unittest.TestCase):
    def test_coen_style_workbook_is_parsed(self) -> None:
        parser = ExcelOrderParser()

        with tempfile.TemporaryDirectory(prefix="order-info-xlsx-") as temp_dir:
            workbook_path = Path(temp_dir) / "coen_order.xlsx"
            workbook = openpyxl.Workbook()
            worksheet = workbook.active
            worksheet["A1"] = "Store #:"
            worksheet["C1"] = "2501"
            worksheet["A2"] = "Location:"
            worksheet["C2"] = "Blue Harbor Market #15"
            worksheet["A3"] = "Delivery Date:"
            worksheet["C3"] = "2026-04-06"
            worksheet["A7"] = 3
            worksheet["B7"] = "Whole Milk Gallon"
            worksheet["C7"] = "cases"
            worksheet["D7"] = 24
            worksheet["G7"] = 31
            worksheet["H7"] = "2% Milk Gallon"
            worksheet["I7"] = "cases"
            worksheet["J7"] = 18
            workbook.save(workbook_path)

            parsed = parser.parse(str(workbook_path))

        self.assertIsNotNone(parsed)
        self.assertEqual(parsed["account_number"], "2501")
        self.assertEqual(parsed["customer_name"], "Blue Harbor Market #15")
        self.assertEqual(len(parsed["line_items"]), 2)


if __name__ == "__main__":
    unittest.main()
