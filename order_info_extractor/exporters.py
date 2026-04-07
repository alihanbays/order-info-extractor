"""ERP-compatible export writer."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import List, Tuple

from order_info_extractor.models import ProcessedOrder
from order_info_extractor.utils import erp_date


class ERPExporter:
    """Write approved orders to a tab-delimited ERP payload and manifest."""

    def __init__(self, export_dir: Path):
        self.export_dir = export_dir
        self.export_dir.mkdir(parents=True, exist_ok=True)

    def write(self, approved_orders: List[ProcessedOrder], run_id: str) -> Tuple[Path, Path]:
        """Write ERP output and a small manifest file."""

        timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        export_path = self.export_dir / f"orders_{timestamp}_{run_id}.txt"
        manifest_path = self.export_dir / f"orders_{timestamp}_{run_id}.manifest.json"

        lines = []
        manifest = {
            "run_id": run_id,
            "approved_orders": len(approved_orders),
            "orders": [],
        }

        for order in approved_orders:
            extraction = order.extraction
            if extraction is None:
                continue

            order_number = extraction.account_number or extraction.customer_name or order.message_id
            header = ["H", str(order_number), "", "", str(extraction.account_number or order_number)]
            header += [""] * 9
            header.append(erp_date(extraction.delivery_date or extraction.order_date))
            lines.append("\t".join(header))

            for item in sorted(extraction.line_items, key=lambda current: int(current.product_number)):
                unit = "EA" if item.unit.lower() in {"ea", "eaches", "each"} else "CASE"
                lines.append(
                    f"D\t{item.product_number}\t{unit}\t{float(item.quantity):.1f}"
                )

            lines.append("E" + "\t" * 18)
            manifest["orders"].append(
                {
                    "message_id": order.message_id,
                    "customer_name": extraction.customer_name,
                    "account_number": extraction.account_number,
                    "line_items": len(extraction.line_items),
                    "total_quantity": extraction.total_quantity(),
                }
            )

        export_path.write_text("\n".join(lines).rstrip() + "\n")
        manifest_path.write_text(json.dumps(manifest, indent=2))
        return export_path, manifest_path

