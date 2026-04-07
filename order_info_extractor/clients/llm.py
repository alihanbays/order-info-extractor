"""LLM-backed and fixture-backed extractors."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, Optional

from openai import OpenAI

from order_info_extractor.config import OpenAIConfig, RetryConfig
from order_info_extractor.models import ExtractedLineItem, InboxMessage, OrderExtraction
from order_info_extractor.utils import clean_html, retry_with_backoff


class OrderLLMClient:
    """Abstract interface implemented by the real and fixture LLM clients."""

    def extract_order(self, message: InboxMessage) -> Optional[OrderExtraction]:
        raise NotImplementedError


class FixtureLLMClient(OrderLLMClient):
    """Use fixture responses so the demo runs without an API key."""

    def __init__(self, response_path: Path):
        self.response_path = response_path
        self.responses: Dict[str, Dict[str, object]] = json.loads(response_path.read_text())

    def extract_order(self, message: InboxMessage) -> Optional[OrderExtraction]:
        payload = self.responses.get(message.id)
        if payload is None:
            return None
        return _build_extraction(payload, parser_name="fixture_llm")


class OpenAILLMClient(OrderLLMClient):
    """OpenAI-backed JSON extraction with retry and compact catalog grounding."""

    def __init__(
        self,
        config: OpenAIConfig,
        retry_config: RetryConfig,
        catalog_prompt: str,
    ):
        self.client = OpenAI(api_key=config.api_key, timeout=config.timeout_seconds)
        self.model = config.model
        self.retry_config = retry_config
        self.catalog_prompt = catalog_prompt

    def extract_order(self, message: InboxMessage) -> Optional[OrderExtraction]:
        body = message.body if message.body_content_type == "text" else clean_html(message.body)
        prompt = f"""
You extract structured B2B order information from forwarded Outlook emails and order notes.

Rules:
- Prefer the original customer details inside forwarded content over the forwarding mailbox.
- Return only products that have explicit quantities.
- Use the product catalog to map product numbers to canonical product names.
- If a field is missing, return an empty string instead of inventing data.

Product catalog:
{self.catalog_prompt}

Return JSON with this schema:
{{
  "customer_name": "",
  "customer_email": "",
  "account_number": "",
  "delivery_date": "YYYY-MM-DD or empty string",
  "order_date": "YYYY-MM-DD or empty string",
  "notes": "",
  "line_items": [
    {{
      "product_number": "",
      "quantity": 0,
      "unit": "",
      "description": ""
    }}
  ]
}}

Message subject: {message.subject}
Message from: {message.sender.address}
Message received: {message.received_at}
Message body:
{body}
"""

        response = retry_with_backoff(
            func=lambda: self.client.chat.completions.create(
                model=self.model,
                response_format={"type": "json_object"},
                temperature=0.0,
                messages=[
                    {
                        "role": "system",
                        "content": "You are a careful order extraction assistant. Respond only with JSON.",
                    },
                    {"role": "user", "content": prompt},
                ],
            ),
            attempts=self.retry_config.attempts,
            base_delay_seconds=self.retry_config.base_delay_seconds,
            max_delay_seconds=self.retry_config.max_delay_seconds,
            jitter_ratio=self.retry_config.jitter_ratio,
            retryable_exceptions=(Exception,),
        )
        payload = json.loads(response.choices[0].message.content)
        return _build_extraction(payload, parser_name="openai_llm")


def _build_extraction(payload: Dict[str, object], parser_name: str) -> OrderExtraction:
    line_items = []
    for line in payload.get("line_items", []):
        line_items.append(
            ExtractedLineItem(
                product_number=str(line.get("product_number", "")).strip(),
                quantity=float(line.get("quantity", 0)),
                unit=str(line.get("unit", "cases")).strip() or "cases",
                description=str(line.get("description", "")).strip(),
            )
        )

    return OrderExtraction(
        customer_name=str(payload.get("customer_name", "")).strip(),
        customer_email=str(payload.get("customer_email", "")).strip(),
        account_number=str(payload.get("account_number", "")).strip(),
        delivery_date=str(payload.get("delivery_date", "")).strip(),
        order_date=str(payload.get("order_date", "")).strip(),
        notes=str(payload.get("notes", "")).strip(),
        parser_name=parser_name,
        source_kind="email_body",
        line_items=line_items,
    )

