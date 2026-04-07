"""
PDF Parser Module
Deterministic parser for PDF purchase orders (e.g. Jordan Banana Company).

Extracts line items matching the pattern:
    Qty  U/M  T XXX  Product Description  Rate  Amount

Uses pdfplumber for text extraction and regex for line item parsing.
"""

import re
from typing import Dict, List, Optional
import pdfplumber


# Known CID-to-character mappings for fonts that don't embed proper Unicode
_CID_MAP = {
    36: "$", 40: "(", 41: ")",
    50: "2", 51: "3", 52: "4",
    69: "E", 75: "K", 78: "N",
    86: "V", 89: "Y",
}

_CID_RE = re.compile(r"\(cid:(\d+)\)")

# Match lines like:  68 ea T 003 Milk Whole Gallon 4-1 Gallon 3.5026 238.18
_LINE_ITEM_RE = re.compile(
    r"^(\d+)\s+"           # qty
    r"(ea|case|5lb\.?)\s+" # unit
    r"T\s+(\d{3})\s+"     # "T XXX" product number
    r"(.+?)"               # description (non-greedy)
    r"(?:\s+[\d,.]+\s+[\d,.]+)?$"  # optional rate + amount at end
)

# Match header lines to extract PO metadata
_PO_NO_RE = re.compile(r"P\.?O\.?\s*(?:No\.?)?\s*[:#]?\s*(\d+)", re.IGNORECASE)
_DATE_RE = re.compile(r"Date\s+P\.O\.", re.IGNORECASE)


def _fix_cid(text: str) -> str:
    """Replace (cid:XX) sequences with their mapped characters."""
    def _replace(m):
        code = int(m.group(1))
        return _CID_MAP.get(code, f"?{code}?")
    return _CID_RE.sub(_replace, text)


def parse_purchase_order(file_path: str) -> Optional[Dict]:
    """
    Parse a PDF purchase order and extract line items.

    Returns:
        Dict with customer_name, account_number, line_items, etc.
        None if no line items found.
    """
    all_text = []
    with pdfplumber.open(file_path) as pdf:
        for page in pdf.pages:
            text = page.extract_text() or ""
            if text:
                all_text.append(text)

    if not all_text:
        return None

    full_text = _fix_cid("\n".join(all_text))
    lines = full_text.split("\n")

    # Extract metadata from first page
    customer_name = ""
    po_number = ""
    delivery_date = ""

    # First non-empty line is usually the company name
    for line in lines:
        stripped = line.strip()
        if stripped and not stripped.startswith("==="):
            customer_name = stripped
            break

    for line in lines[:20]:
        # PO number — look for a standalone number after a date on the same line
        # e.g. "203 Washington Avenue 2/2/2024 12279"
        if not po_number:
            m = _PO_NO_RE.search(line)
            if m:
                po_number = m.group(1)
            else:
                # PO number at end of a line that also has a date
                po_match = re.search(r'\d{1,2}/\d{1,2}/\d{2,4}\s+(\d{4,})', line)
                if po_match:
                    po_number = po_match.group(1)

        # Expected Date = delivery date (e.g. "Expected Date 2/1/2024")
        exp_match = re.search(r'Expected\s+Date\s+(\d{1,2}/\d{1,2}/\d{2,4})', line, re.IGNORECASE)
        if exp_match:
            delivery_date = exp_match.group(1)

    # Extract line items
    line_items = []
    for line in lines:
        m = _LINE_ITEM_RE.match(line.strip())
        if not m:
            continue

        qty_str, unit, prod_num, desc = m.groups()
        qty = int(qty_str)
        if qty <= 0:
            continue

        # Clean product number (remove leading zeros)
        prod_num_clean = str(int(prod_num))

        # Clean description — strip trailing price/amount numbers
        desc = re.sub(r'\s+[\d,.]+\s*$', '', desc).strip()

        line_items.append({
            'product_number': prod_num_clean,
            'quantity': float(qty),
            'unit': unit,
            'description': desc,
        })

    if not line_items:
        return None

    return {
        'customer_name': customer_name,
        'account_number': po_number,
        'delivery_date': delivery_date,
        'line_items': line_items,
        'total_items': len(line_items),
        'total_quantity': sum(i['quantity'] for i in line_items),
    }


def is_pdf_file(filename: str) -> bool:
    """Check if a file is a PDF."""
    return filename.lower().endswith(".pdf")
