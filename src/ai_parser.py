"""Compatibility wrapper for LLM-based order extraction."""

from __future__ import annotations

from pathlib import Path
from typing import Dict, Optional

from order_info_extractor.catalog import ProductCatalog
from order_info_extractor.clients.llm import OpenAILLMClient
from order_info_extractor.config import OpenAIConfig, RetryConfig
from order_info_extractor.models import EmailAddress, InboxMessage


class AIParser:
    """Backwards-compatible adapter around the production LLM extractor."""

    def __init__(self, config: Dict):
        if not config.get("api_key"):
            raise ValueError("OpenAI API key is required for the compatibility AI parser.")

        catalog = ProductCatalog(Path(__file__).parent / "product_catalog.json")
        self.client = OpenAILLMClient(
            config=OpenAIConfig.model_validate(config),
            retry_config=RetryConfig(),
            catalog_prompt=catalog.compact_prompt_view(),
        )

    def extract_order_info(self, email: Dict) -> Optional[Dict]:
        """Extract order information from an email dictionary."""

        body = email.get("body", {})
        sender = email.get("from", {}).get("emailAddress", {})
        message = InboxMessage(
            id=email.get("id", "legacy-email"),
            internetMessageId=email.get("internetMessageId", ""),
            subject=email.get("subject", ""),
            sender=EmailAddress(
                name=sender.get("name", ""),
                address=sender.get("address", ""),
            ),
            receivedAt=email.get("receivedDateTime", ""),
            body=body.get("content", ""),
            bodyContentType=body.get("contentType", "html"),
        )
        result = self.client.extract_order(message)
        return result.model_dump() if result else None

    def extract_from_attachment_text(
        self, text: str, filename: str = "", email_metadata: Dict = None
    ) -> Optional[Dict]:
        """Extract order information from text converted from an attachment."""

        metadata = email_metadata or {}
        sender = metadata.get("from", {}).get("emailAddress", {})
        message = InboxMessage(
            id=metadata.get("id", f"legacy-{filename or 'attachment'}"),
            internetMessageId=metadata.get("internetMessageId", ""),
            subject=metadata.get("subject", filename),
            sender=EmailAddress(
                name=sender.get("name", ""),
                address=sender.get("address", ""),
            ),
            receivedAt=metadata.get("receivedDateTime", ""),
            body=text,
            bodyContentType="text",
        )
        result = self.client.extract_order(message)
        return result.model_dump() if result else None

    @staticmethod
    def validate_order_info(order_info: Dict) -> bool:
        """Check whether the order contains the minimum required fields."""

        return bool(order_info and order_info.get("customer_name"))
