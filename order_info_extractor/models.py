"""Typed domain models used throughout the ingestion pipeline."""

from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field


class EmailAddress(BaseModel):
    """Represents a sender or recipient."""

    name: str = ""
    address: str = ""


class MessageAttachment(BaseModel):
    """Normalized attachment payload."""

    filename: str
    content_bytes: bytes = b""
    content_type: str = "application/octet-stream"


class InboxMessage(BaseModel):
    """A normalized email/message that can be processed by the pipeline."""

    model_config = ConfigDict(populate_by_name=True)

    id: str
    internet_message_id: str = Field(default="", alias="internetMessageId")
    subject: str = ""
    sender: EmailAddress = Field(default_factory=EmailAddress)
    received_at: str = Field(default="", alias="receivedAt")
    body: str = ""
    body_content_type: str = Field(default="text", alias="bodyContentType")
    attachments: List[MessageAttachment] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)

    @property
    def has_attachments(self) -> bool:
        return bool(self.attachments)


class ExtractedLineItem(BaseModel):
    """Structured line item extracted from an email or attachment."""

    product_number: str
    quantity: float
    unit: str = "cases"
    product: str = ""
    category: str = ""
    description: str = ""


class OrderExtraction(BaseModel):
    """Candidate order parsed from the source message."""

    customer_name: str = ""
    customer_email: str = ""
    account_number: str = ""
    delivery_date: str = ""
    order_date: str = ""
    notes: str = ""
    parser_name: str
    source_kind: Literal["email_body", "attachment"] = "email_body"
    source_filename: str = ""
    line_items: List[ExtractedLineItem] = Field(default_factory=list)

    def total_quantity(self) -> float:
        return sum(item.quantity for item in self.line_items)


class ValidationIssue(BaseModel):
    """A validation issue raised after extraction."""

    code: str
    severity: Literal["warning", "error"]
    message: str
    field: str = ""
    suggestion: str = ""


class ProcessedOrder(BaseModel):
    """Final processing outcome for a single source message."""

    message_id: str
    idempotency_key: str
    source_hash: str
    status: Literal["approved", "manual_review", "skipped"]
    confidence: float = 0.0
    extraction: Optional[OrderExtraction] = None
    validation_issues: List[ValidationIssue] = Field(default_factory=list)
    export_path: str = ""
    review_path: str = ""
    notes: str = ""


class PipelineSummary(BaseModel):
    """Aggregated outcome for a full pipeline run."""

    run_id: str
    processed_orders: List[ProcessedOrder] = Field(default_factory=list)
    export_path: str = ""
    manifest_path: str = ""
    approved_count: int = 0
    review_count: int = 0
    skipped_count: int = 0

