"""Core ingestion pipeline orchestration."""

from __future__ import annotations

import json
import logging
import tempfile
import uuid
from pathlib import Path
from typing import List, Optional, Tuple

from order_info_extractor.catalog import ProductCatalog
from order_info_extractor.config import AppConfig
from order_info_extractor.exporters import ERPExporter
from order_info_extractor.models import (
    ExtractedLineItem,
    InboxMessage,
    OrderExtraction,
    PipelineSummary,
    ProcessedOrder,
    ValidationIssue,
)
from order_info_extractor.state import SQLiteStateStore
from order_info_extractor.utils import message_hash, parse_date
from src.excel_parser import ExcelOrderParser, is_excel_file
from src.pdf_parser import is_pdf_file, parse_purchase_order


class IngestionPipeline:
    """Process messages from the inbox, validate them, and export approved orders."""

    def __init__(
        self,
        config: AppConfig,
        inbox_client,
        llm_client,
        catalog: ProductCatalog,
        exporter: ERPExporter,
        state_store: SQLiteStateStore,
        logger: logging.Logger,
    ):
        self.config = config
        self.inbox_client = inbox_client
        self.llm_client = llm_client
        self.catalog = catalog
        self.exporter = exporter
        self.state_store = state_store
        self.logger = logger
        self.excel_parser = ExcelOrderParser()

    def run(
        self,
        limit: int = 25,
        subject_filter: Optional[str] = None,
        from_date: Optional[str] = None,
        force: bool = False,
    ) -> PipelineSummary:
        """Execute the full pipeline for the selected message range."""

        run_id = uuid.uuid4().hex[:8]
        processed_orders: List[ProcessedOrder] = []
        approved_orders: List[ProcessedOrder] = []
        seen_in_run = {}

        messages = self.inbox_client.fetch_messages(
            limit=limit,
            subject_filter=subject_filter,
            from_date=from_date,
        )
        self.logger.info(
            "Fetched messages for processing",
            extra={"event": "messages_fetched", "status": "ok"},
        )

        for message in messages:
            processed = self._process_message(
                message=message,
                force=force,
                seen_in_run=seen_in_run,
            )
            processed_orders.append(processed)
            if processed.status == "approved":
                approved_orders.append(processed)

        export_path = ""
        manifest_path = ""
        if approved_orders:
            export_file, manifest_file = self.exporter.write(approved_orders, run_id=run_id)
            export_path = str(export_file)
            manifest_path = str(manifest_file)
            for processed in approved_orders:
                processed.export_path = export_path
                self.state_store.record(processed)

        summary = PipelineSummary(
            run_id=run_id,
            processed_orders=processed_orders,
            export_path=export_path,
            manifest_path=manifest_path,
            approved_count=sum(1 for item in processed_orders if item.status == "approved"),
            review_count=sum(1 for item in processed_orders if item.status == "manual_review"),
            skipped_count=sum(1 for item in processed_orders if item.status == "skipped"),
        )
        self._write_run_manifest(summary)
        return summary

    def _process_message(self, message: InboxMessage, force: bool, seen_in_run: dict) -> ProcessedOrder:
        source_hash = message_hash(message)
        idempotency_key = message.internet_message_id or message.id or source_hash

        if seen_in_run.get(idempotency_key) == source_hash:
            processed = ProcessedOrder(
                message_id=message.id,
                idempotency_key=idempotency_key,
                source_hash=source_hash,
                status="skipped",
                notes="Skipped because an identical payload already appeared in this batch.",
            )
            self.logger.info(
                "Skipped duplicate message already seen in this run",
                extra={
                    "event": "message_skipped",
                    "message_id": message.id,
                    "status": processed.status,
                    "confidence": processed.confidence,
                },
            )
            return processed

        if not force:
            existing = self.state_store.lookup(idempotency_key=idempotency_key, source_hash=source_hash)
            if existing:
                processed = ProcessedOrder(
                    message_id=message.id,
                    idempotency_key=idempotency_key,
                    source_hash=source_hash,
                    status="skipped",
                    confidence=float(existing["confidence"]),
                    export_path=existing["export_path"],
                    review_path=existing["review_path"],
                    notes="Skipped because an identical payload was already processed.",
                )
                self.logger.info(
                    "Skipped duplicate message",
                    extra={
                        "event": "message_skipped",
                        "message_id": message.id,
                        "status": processed.status,
                        "confidence": processed.confidence,
                    },
                )
                return processed

        seen_in_run[idempotency_key] = source_hash
        extraction, issues = self._extract_and_validate(message)
        confidence = self._score_confidence(extraction=extraction, issues=issues)
        status = self._status_for(confidence=confidence, issues=issues)

        processed = ProcessedOrder(
            message_id=message.id,
            idempotency_key=idempotency_key,
            source_hash=source_hash,
            status=status,
            confidence=confidence,
            extraction=extraction,
            validation_issues=issues,
        )

        if status == "manual_review":
            processed.review_path = str(self._write_review_case(processed))

        self.state_store.record(processed)
        self.logger.info(
            "Processed message",
            extra={
                "event": "message_processed",
                "message_id": message.id,
                "status": status,
                "confidence": round(confidence, 3),
            },
        )
        return processed

    def _extract_and_validate(
        self, message: InboxMessage
    ) -> Tuple[OrderExtraction, List[ValidationIssue]]:
        attachment_result = self._extract_from_attachments(message)
        if attachment_result is not None:
            extraction = attachment_result
        else:
            llm_result = self.llm_client.extract_order(message)
            if llm_result is None:
                extraction = OrderExtraction(
                    customer_name="",
                    customer_email=message.sender.address,
                    account_number="",
                    delivery_date="",
                    order_date=parse_date(message.received_at),
                    notes="LLM parser returned no extraction result.",
                    parser_name="llm_unavailable",
                    source_kind="email_body",
                    line_items=[],
                )
            else:
                llm_result.customer_email = llm_result.customer_email or message.sender.address
                llm_result.order_date = llm_result.order_date or parse_date(message.received_at)
                extraction = llm_result

        return self.catalog.enrich_and_validate(extraction)

    def _extract_from_attachments(self, message: InboxMessage) -> Optional[OrderExtraction]:
        for attachment in message.attachments:
            filename = attachment.filename
            if not (is_excel_file(filename) or is_pdf_file(filename)):
                continue

            suffix = Path(filename).suffix.lower() or ".bin"
            with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as temp_file:
                temp_file.write(attachment.content_bytes)
                temp_path = Path(temp_file.name)

            try:
                if is_excel_file(filename):
                    parsed = self.excel_parser.parse(str(temp_path))
                    parser_name = "excel_attachment"
                else:
                    parsed = parse_purchase_order(str(temp_path))
                    parser_name = "pdf_attachment"
            finally:
                temp_path.unlink(missing_ok=True)

            if not parsed:
                continue

            line_items = [
                ExtractedLineItem(
                    product_number=str(item.get("product_number", "")).strip(),
                    quantity=float(item.get("quantity", 0)),
                    unit=str(item.get("unit", "cases")).strip() or "cases",
                    description=str(item.get("description", "")).strip(),
                    product=str(item.get("product", "")).strip(),
                    category=str(item.get("category", "")).strip(),
                )
                for item in parsed.get("line_items", [])
            ]
            return OrderExtraction(
                customer_name=str(parsed.get("customer_name", "")).strip(),
                customer_email=message.sender.address,
                account_number=str(parsed.get("account_number", "")).strip(),
                delivery_date=str(parsed.get("delivery_date", "")).strip(),
                order_date=parse_date(message.received_at),
                notes=str(parsed.get("notes", "")).strip(),
                parser_name=parser_name,
                source_kind="attachment",
                source_filename=filename,
                line_items=line_items,
            )
        return None

    def _score_confidence(
        self, extraction: OrderExtraction, issues: List[ValidationIssue]
    ) -> float:
        base = 0.93 if extraction.source_kind == "attachment" else 0.74
        if extraction.account_number:
            base += 0.05
        if extraction.delivery_date:
            base += 0.04
        if extraction.customer_email:
            base += 0.02
        if extraction.line_items:
            base += min(0.06, 0.02 * len(extraction.line_items))

        for issue in issues:
            base -= 0.2 if issue.severity == "error" else 0.06

        return max(0.0, min(0.99, round(base, 3)))

    def _status_for(self, confidence: float, issues: List[ValidationIssue]) -> str:
        has_errors = any(issue.severity == "error" for issue in issues)
        if has_errors or confidence < self.config.confidence_threshold:
            return "manual_review"
        return "approved"

    def _write_review_case(self, processed: ProcessedOrder) -> Path:
        review_dir = self.config.output_path(self.config.paths.review_dir)
        review_dir.mkdir(parents=True, exist_ok=True)
        review_path = review_dir / f"{processed.message_id}.json"
        review_path.write_text(
            json.dumps(
                {
                    "message_id": processed.message_id,
                    "confidence": processed.confidence,
                    "issues": [issue.model_dump() for issue in processed.validation_issues],
                    "extraction": processed.extraction.model_dump() if processed.extraction else None,
                },
                indent=2,
            )
        )
        return review_path

    def _write_run_manifest(self, summary: PipelineSummary) -> None:
        run_dir = self.config.output_path(self.config.paths.runs_dir)
        run_dir.mkdir(parents=True, exist_ok=True)
        manifest_path = run_dir / f"run_{summary.run_id}.json"
        summary.manifest_path = str(manifest_path)
        manifest_path.write_text(json.dumps(summary.model_dump(), indent=2))
