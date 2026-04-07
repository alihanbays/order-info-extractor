"""Product catalog loading, enrichment, and validation."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, List, Tuple

from order_info_extractor.models import OrderExtraction, ValidationIssue
from order_info_extractor.utils import parse_date


class ProductCatalog:
    """Validate extracted line items against a canonical product catalog."""

    def __init__(self, catalog_path: Path):
        self.catalog_path = catalog_path
        self.entries: Dict[str, Dict[str, str]] = json.loads(catalog_path.read_text())

    def compact_prompt_view(self) -> str:
        """Small text view used to anchor the LLM prompt."""

        lines = []
        for product_number in sorted(self.entries.keys(), key=lambda value: int(value)):
            entry = self.entries[product_number]
            lines.append(
                f"#{product_number}: {entry['product']} ({entry['category']})"
            )
        return "\n".join(lines)

    def enrich_and_validate(
        self, extraction: OrderExtraction
    ) -> Tuple[OrderExtraction, List[ValidationIssue]]:
        """Enrich canonical product metadata and return validation issues."""

        issues: List[ValidationIssue] = []
        seen = set()

        extraction.delivery_date = parse_date(extraction.delivery_date)
        extraction.order_date = parse_date(extraction.order_date)

        if not extraction.customer_name:
            issues.append(
                ValidationIssue(
                    code="missing_customer_name",
                    severity="error",
                    field="customer_name",
                    message="Customer name is required for downstream export.",
                    suggestion="Confirm the original sender or store name.",
                )
            )

        if not extraction.account_number:
            issues.append(
                ValidationIssue(
                    code="missing_account_number",
                    severity="warning",
                    field="account_number",
                    message="Account number is missing and should be reviewed before export.",
                    suggestion="Confirm the ERP customer account number.",
                )
            )

        if not extraction.delivery_date:
            issues.append(
                ValidationIssue(
                    code="missing_delivery_date",
                    severity="warning",
                    field="delivery_date",
                    message="No delivery date was extracted from the order.",
                    suggestion="Verify the requested ship or delivery date.",
                )
            )

        if not extraction.line_items:
            issues.append(
                ValidationIssue(
                    code="no_line_items",
                    severity="error",
                    field="line_items",
                    message="No line items were extracted from the message.",
                    suggestion="Check the source document and parsing response.",
                )
            )

        for item in extraction.line_items:
            item.product_number = str(item.product_number).strip()
            item.unit = (item.unit or "cases").strip() or "cases"

            if item.quantity <= 0:
                issues.append(
                    ValidationIssue(
                        code="invalid_quantity",
                        severity="error",
                        field="quantity",
                        message=f"Line item {item.product_number} has a non-positive quantity.",
                    )
                )

            if item.product_number in seen:
                issues.append(
                    ValidationIssue(
                        code="duplicate_product_number",
                        severity="warning",
                        field="product_number",
                        message=f"Product {item.product_number} appears multiple times in the same order.",
                    )
                )
            seen.add(item.product_number)

            catalog_entry = self.entries.get(item.product_number)
            if catalog_entry is None:
                issues.append(
                    ValidationIssue(
                        code="unknown_product",
                        severity="error",
                        field="product_number",
                        message=f"Product {item.product_number} was not found in the catalog.",
                        suggestion="Update the catalog or manually map the line item.",
                    )
                )
                continue

            item.product = catalog_entry["product"]
            item.category = catalog_entry["category"]

        return extraction, issues

