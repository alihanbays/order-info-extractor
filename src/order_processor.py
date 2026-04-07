"""
Order Processor Module
Coordinates extraction of order information from emails.

Attachments (.xlsx, .xls, .pdf) are parsed programmatically.
Plain-text email bodies are parsed with the AI.
"""

from typing import Dict, List, Optional
from pathlib import Path
import tempfile

from src.ai_parser import AIParser
from src.excel_parser import ExcelOrderParser, is_excel_file
from src import pdf_parser


class OrderProcessor:
    """
    Process orders from emails:
    1. Excel attachments — deterministic column-based parser
    2. PDF attachments   — deterministic regex-based parser
    3. Plain-text emails  — AI parser (with product catalog)
    """

    def __init__(self, ai_parser: AIParser):
        self.ai_parser = ai_parser
        self.excel_parser = ExcelOrderParser()

    def process_email(self, email: Dict, attachments: List[Dict] = None) -> Optional[Dict]:
        """Process an email and extract order information."""
        if attachments:
            result = self._process_attachments(attachments, email)
            if result:
                return result

        # Fallback: parse the email body text with AI
        return self._process_text_order(email)

    # ------------------------------------------------------------------
    # Attachment handling (deterministic — no AI)
    # ------------------------------------------------------------------

    def _process_attachments(self, attachments: List[Dict], email: Dict) -> Optional[Dict]:
        """Try every supported attachment and return the first successful parse."""
        for attachment in attachments:
            filename = attachment.get('filename', '')
            file_content = attachment.get('data')
            if not file_content:
                continue
            if not (is_excel_file(filename) or pdf_parser.is_pdf_file(filename)):
                continue

            try:
                result = self._parse_attachment(file_content, filename, email)
                if result:
                    return result
            except Exception as e:
                print(f"Error processing attachment {filename}: {e}")
                continue

        return None

    def _parse_attachment(
        self, file_content: bytes, filename: str, email: Dict
    ) -> Optional[Dict]:
        """Write attachment to temp file, parse it, return normalised order."""
        suffix = Path(filename).suffix.lower() or '.bin'
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
            tmp.write(file_content)
            tmp_path = tmp.name

        try:
            if is_excel_file(filename):
                parsed = self.excel_parser.parse(tmp_path)
            elif pdf_parser.is_pdf_file(filename):
                parsed = pdf_parser.parse_purchase_order(tmp_path)
            else:
                return None
        finally:
            Path(tmp_path).unlink(missing_ok=True)

        if not parsed or not parsed.get('line_items'):
            return None

        return self._normalise(parsed, email, filename)

    # ------------------------------------------------------------------
    # Text (email body) handling — AI
    # ------------------------------------------------------------------

    def _process_text_order(self, email: Dict) -> Optional[Dict]:
        """Extract order from email body text using AI."""
        try:
            order_data = self.ai_parser.extract_order_info(email)
            if order_data:
                return self._normalise(order_data, email)
        except Exception as e:
            print(f"Error parsing text order: {e}")
        return None

    # ------------------------------------------------------------------
    # Normalisation
    # ------------------------------------------------------------------

    @staticmethod
    def _normalise(data: Dict, email: Dict, filename: str = '') -> Dict:
        """Normalise parsed data (from any source) to the standard order dict."""
        line_items = data.get('line_items', [])

        total_items = len(line_items)
        total_quantity = sum(
            float(item.get('quantity', 0))
            for item in line_items
            if item.get('quantity')
        )

        if line_items:
            parts = []
            for item in line_items[:5]:
                qty = item.get('quantity', '')
                prod = item.get('product', item.get('description', 'Unknown'))
                parts.append(f"{qty}x {prod}")
            summary = ", ".join(parts)
            if len(line_items) > 5:
                summary += f" ... and {len(line_items) - 5} more"
        else:
            summary = "No items"

        return {
            'order_type': data.get('order_type', 'attachment' if filename else 'text_email'),
            'order_id': data.get('order_id', data.get('account_number', 'N/A')),
            'customer_name': data.get('customer_name', 'Unknown'),
            'customer_email': (
                data.get('customer_email')
                or email.get('from', {}).get('emailAddress', {}).get('address', '')
            ),
            'account_number': data.get('account_number', 'N/A'),
            'delivery_date': data.get('delivery_date', 'N/A'),
            'order_date': data.get('order_date', email.get('receivedDateTime', '')),
            'line_items': line_items,
            'total_items': total_items,
            'total_quantity': total_quantity,
            'order_summary': summary,
            'source_email_subject': email.get('subject', ''),
            'attachment_filename': filename,
            'notes': data.get('notes', ''),
            'status': 'Pending',
        }
