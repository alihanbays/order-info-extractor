"""
Excel Parser Module
Deterministic parsers for common spreadsheet order form attachments.

Supports two known form layouts:
  1. Coen-style (.xlsx) — "Store #:" in A1, columns: Line#/Description/Sell Unit/Eaches/Pars
  2. Legacy ERP-style (.xls) — "#/QTY/PRODUCT" headers in row 2, 3 parallel sections
"""

from typing import Dict, List, Optional, Tuple
import openpyxl
import xlrd
from pathlib import Path
import re


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _to_int_str(val) -> Optional[str]:
    """Normalise a product number cell to a clean string like '3' or '115'."""
    if val is None:
        return None
    if isinstance(val, float):
        if val != int(val):
            return None
        return str(int(val))
    s = str(val).strip().lstrip("0")
    if s and s.isdigit():
        return s
    return None


def _to_qty(val) -> Optional[float]:
    """Return a positive numeric quantity, or None."""
    if val is None:
        return None
    if isinstance(val, (int, float)):
        return float(val) if val > 0 else None
    s = str(val).strip()
    try:
        f = float(s)
        return f if f > 0 else None
    except (ValueError, TypeError):
        return None


_CASE_UNIT_NORM = {
    'pint':   'Pt / Each',
    'pints':  'Pt / Each',
    'quart':  'Qt / Each',
    'quarts': 'Qt / Each',
}


def _expand_case_unit(sell_unit: str, case_qty: float):
    """Expand a Case-column quantity using the sell-unit pack size.

    Sell units like '5 Pints' or '12 Quarts' encode how many individual
    items are in one case.  2 cases of '5 Pints' → (10.0, 'Pt / Each').
    """
    m = re.match(r'^(\d+)\s+([A-Za-z]+)$', sell_unit.strip())
    if not m:
        return sell_unit, case_qty

    pack_size = int(m.group(1))
    raw_unit = m.group(2).lower()
    unit = _CASE_UNIT_NORM.get(raw_unit, sell_unit)
    return unit, case_qty * pack_size


def _cell_xlsx(ws, row: int, col: int):
    """Read an openpyxl cell (1-based row/col)."""
    return ws.cell(row, col).value


def _cell_xls(ws, row: int, col: int):
    """Read an xlrd cell (converted from 1-based to 0-based)."""
    try:
        return ws.cell_value(row - 1, col - 1)
    except IndexError:
        return None


# ---------------------------------------------------------------------------
# Coen-style form (.xlsx)
# ---------------------------------------------------------------------------
# Layout:
#   Row 1: "Store #:" (A1), store number (C1)
#   Row 2: "Location:" (A2), value (C2)
#   Row 3: "Delivery Date:" (A3), value (C3)
#   Row 6: column headers
#   Row 7+: products in 3 parallel sections
#
#   Left   (A-E):  A=Line#, B=Desc, C=Sell Unit, D=Eaches, E=Pars
#   Middle (G-K):  G=Line#, H=Desc, I=Sell Unit, J=Eaches, K=Pars
#   Right  (M-R):  M=Line#, N=Desc, O=Sell Unit, P=Case, Q=Eaches, R=Pars

# (product_num_col, qty_cols, desc_col, unit_col, case_qty_cols)  — 1-based
_COEN_SECTIONS = [
    (1,  [4],      2, 3,  set()),   # A=prod#, D=eaches
    (7,  [10],     8, 9,  set()),   # G=prod#, J=eaches
    (13, [16, 17], 14, 15, {16}),   # M=prod#, P=case, Q=eaches
]


def _parse_coen(ws) -> Optional[Dict]:
    """Parse a Coen-style .xlsx order form using openpyxl worksheet."""
    cell = lambda r, c: _cell_xlsx(ws, r, c)

    # Detect: A1 must contain "Store"
    a1 = str(cell(1, 1) or '')
    if 'store' not in a1.lower():
        return None

    # Header info
    store_num = str(cell(1, 3) or '').strip()
    location = str(cell(2, 3) or '').strip()
    delivery_raw = cell(3, 3)
    if delivery_raw:
        delivery_date = str(delivery_raw).strip()
        # Handle datetime objects
        if hasattr(delivery_raw, 'strftime'):
            delivery_date = delivery_raw.strftime('%Y-%m-%d')
    else:
        delivery_date = ''

    customer_name = location if location else f"Store #{store_num}"

    # Scan for line items
    line_items = []
    for row in range(7, 60):
        # Skip rows that contain "Total"
        for c in range(1, 19):
            v = cell(row, c)
            if isinstance(v, str) and 'total' in v.lower():
                break
        else:
            # No "Total" found — scan sections
            for prod_col, qty_cols, desc_col, unit_col, case_qty_cols in _COEN_SECTIONS:
                prod_num = _to_int_str(cell(row, prod_col))
                if not prod_num:
                    continue

                for qc in qty_cols:
                    qty = _to_qty(cell(row, qc))
                    if qty is not None:
                        desc = str(cell(row, desc_col) or '').strip()
                        unit = str(cell(row, unit_col) or 'cases').strip()
                        # Case column: expand pack-size units like '5 Pints'
                        if qc in case_qty_cols:
                            unit, qty = _expand_case_unit(unit, qty)
                        line_items.append({
                            'product_number': prod_num,
                            'quantity': qty,
                            'unit': unit,
                            'description': desc,
                        })
                        break  # don't double-count if both Case and Eaches are filled

    if not line_items:
        return None

    return {
        'customer_name': customer_name,
        'account_number': store_num,
        'delivery_date': delivery_date,
        'line_items': line_items,
        'total_items': len(line_items),
        'total_quantity': sum(i['quantity'] for i in line_items),
    }


# ---------------------------------------------------------------------------
# Legacy ERP-style form (.xls)
# ---------------------------------------------------------------------------
# Layout:
#   Row 2: "#", "QTY", "PRODUCT" repeated in cols B-D, F-H, J-L
#   Row 7, Col M: "Delivery Date:"
#   Row 22, Col M: "Acct Name: / Acct #:"
#   Row 4+: Category(A/E/I), #(B/F/J), QTY(C/G/K), Product(D/H/L)

# (product_num_col, qty_col, desc_col) — 1-based
_TURNER_SECTIONS = [
    (2, 3, 4),    # B=#, C=QTY, D=product
    (6, 7, 8),    # F=#, G=QTY, H=product
    (10, 11, 12), # J=#, K=QTY, L=product
]


def _parse_turner_xls(file_path: str) -> Optional[Dict]:
    """Parse a legacy ERP-style .xls order form using xlrd."""
    wb = xlrd.open_workbook(file_path)
    ws = wb.sheet_by_index(0)
    cell = lambda r, c: _cell_xls(ws, r, c)

    # Detect: B2 should be "#" or close to it
    b2 = str(cell(2, 2) or '').strip()
    if b2 != '#':
        return None

    # Header info
    delivery_date = ''
    raw = cell(7, 13)
    if raw and 'delivery' not in str(raw).lower():
        delivery_date = str(raw).strip()

    acct_info = str(cell(22, 13) or '').strip()
    account_name = ''
    account_number = ''
    if acct_info and 'acct' not in acct_info.lower():
        parts = acct_info.split('\n')
        account_name = parts[0].strip() if parts else ''
        if len(parts) >= 2:
            nums = re.findall(r'\d+', parts[1])
            account_number = nums[0] if nums else ''

    # Scan for line items
    line_items = []
    for row in range(3, 80):
        for prod_col, qty_col, desc_col in _TURNER_SECTIONS:
            prod_num = _to_int_str(cell(row, prod_col))
            if not prod_num:
                continue

            qty = _to_qty(cell(row, qty_col))
            if qty is None:
                continue

            desc = str(cell(row, desc_col) or '').strip()
            line_items.append({
                'product_number': prod_num,
                'quantity': qty,
                'unit': 'cases',
                'description': desc,
            })

    if not line_items:
        return None

    return {
        'customer_name': account_name or 'Unknown',
        'account_number': account_number,
        'delivery_date': delivery_date,
        'line_items': line_items,
        'total_items': len(line_items),
        'total_quantity': sum(i['quantity'] for i in line_items),
    }


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

class ExcelOrderParser:
    """Deterministic parser for recurring Excel order form layouts."""

    def parse(self, file_path: str) -> Optional[Dict]:
        """
        Parse an Excel order form. Auto-detects the supported spreadsheet layouts.

        Returns:
            Normalised order dict or None if no filled quantities found.
        """
        ext = Path(file_path).suffix.lower()

        if ext == '.xls':
            return _parse_turner_xls(file_path)

        # .xlsx — try Coen first, then fall back to future detectors
        try:
            wb = openpyxl.load_workbook(file_path, data_only=True)
            ws = wb.active
        except Exception as e:
            raise Exception(f"Cannot open {file_path}: {e}")

        result = _parse_coen(ws)
        if result:
            return result

        # Could add more format detectors here in the future
        return None


def is_excel_file(filename: str) -> bool:
    """Check if a file is an Excel file."""
    extensions = ['.xlsx', '.xls', '.xlsm']
    return any(filename.lower().endswith(ext) for ext in extensions)
