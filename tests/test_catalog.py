"""Unit tests for catalog validation and enrichment."""

from __future__ import annotations

import unittest
from pathlib import Path

from order_info_extractor.catalog import ProductCatalog
from order_info_extractor.models import ExtractedLineItem, OrderExtraction


class CatalogValidationTests(unittest.TestCase):
    def test_unknown_products_raise_validation_errors(self) -> None:
        catalog = ProductCatalog(Path("src/product_catalog.json"))
        extraction = OrderExtraction(
            customer_name="Night Owl Cafe",
            customer_email="sam@nightowl.example",
            account_number="",
            delivery_date="2026-04-06",
            order_date="2026-04-05",
            parser_name="fixture_llm",
            line_items=[
                ExtractedLineItem(product_number="83", quantity=4, unit="cases"),
                ExtractedLineItem(product_number="999", quantity=2, unit="cases"),
            ],
        )

        _, issues = catalog.enrich_and_validate(extraction)
        codes = {issue.code for issue in issues}

        self.assertIn("unknown_product", codes)
        self.assertIn("missing_account_number", codes)


if __name__ == "__main__":
    unittest.main()
