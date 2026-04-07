"""
ERP Order File Writer
Generates tab-delimited text files in a simple H/D/E ERP batch format.

Format (15-column H, 4-column D, 19-column E):
    H\tOrder#\t\t\tCustomer#\t(9 empty)\tdate
    D\tproduct#\tunit\tquantity
    E\t(18 empty tabs)
    (repeats for each order)
"""

from typing import List, Dict
from pathlib import Path
from datetime import datetime


class ERPWriter:
    """Write orders in the H/D/E ERP text format."""

    def __init__(self, output_dir: str = "output"):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def write_orders(self, orders: List[Dict], filename: str = None) -> str:
        """
        Write all orders to a single ERP text file.

        Each order is a block of H / D... / E lines.
        Multiple orders are appended sequentially.

        Args:
            orders: List of normalized order dictionaries.
            filename: Optional custom filename.

        Returns:
            Path to the created text file.
        """
        if not filename:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"orders_{timestamp}.txt"

        filepath = self.output_dir / filename
        lines: list[str] = []

        for order in orders:
            order_number = order.get("account_number") or order.get("order_id") or "0"
            customer_number = order.get("account_number") or "0"
            order_date = self._format_date(
                order.get("order_date") or order.get("delivery_date") or ""
            )

            # H line — Header (15 columns)
            h_fields = ["H", str(order_number), "", "", str(customer_number)]
            h_fields += [""] * 9
            h_fields.append(order_date)
            lines.append("\t".join(h_fields))

            # D lines — one per line item, sorted by product number (lexicographic)
            sorted_items = sorted(
                order.get("line_items", []),
                key=lambda item: str(item.get("product_number", "0")).strip(),
            )
            for item in sorted_items:
                product_number = str(item.get("product_number", "0")).strip()
                raw_unit = str(item.get("unit", "EA")).strip().upper()
                unit = "EA" if raw_unit == "EA" else "CASE"
                raw_qty = item.get("quantity", 0)
                try:
                    quantity = f"{float(raw_qty):.1f}"
                except (ValueError, TypeError):
                    quantity = str(raw_qty).strip()
                lines.append(f"D\t{product_number}\t{unit}\t{quantity}")

            # E line — End of order (19 columns)
            lines.append("E" + "\t" * 18)

        content = "\n".join(lines) + "\n"
        filepath.write_text(content)
        return str(filepath)

    @staticmethod
    def _format_date(date_str: str) -> str:
        """
        Normalise various date representations to M/D/YYYY for the ERP.

        Handles ISO (2026-02-18), slash (2/18/26), and passthrough.
        """
        if not date_str:
            dt = datetime.now()
            return f"{dt.month}/{dt.day}/{dt.year}"

        # Try ISO format first (YYYY-MM-DD or YYYY-MM-DDTHH:MM:SS)
        for fmt in ("%Y-%m-%d", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M:%SZ"):
            try:
                dt = datetime.strptime(date_str[:len("2026-02-18T00:00:00Z")], fmt)
                return f"{dt.month}/{dt.day}/{dt.year}"
            except ValueError:
                continue

        # Already short? Return as-is.
        return date_str
