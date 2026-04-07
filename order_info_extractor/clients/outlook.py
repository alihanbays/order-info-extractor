"""Message source clients for fixture inboxes and Microsoft Graph."""

from __future__ import annotations

import base64
import json
from datetime import datetime
from pathlib import Path
from typing import List, Optional

import msal
import requests

from order_info_extractor.config import RetryConfig, SourceConfig
from order_info_extractor.models import EmailAddress, InboxMessage, MessageAttachment
from order_info_extractor.utils import retry_with_backoff


class InboxClient:
    """Abstract inbox client."""

    def fetch_messages(
        self,
        limit: int,
        subject_filter: Optional[str] = None,
        from_date: Optional[str] = None,
    ) -> List[InboxMessage]:
        raise NotImplementedError


class FixtureInboxClient(InboxClient):
    """Read mock Outlook messages from a local JSON fixture file."""

    def __init__(self, fixture_path: Path):
        self.fixture_path = fixture_path
        self.messages = self._load_messages()

    def _load_messages(self) -> List[InboxMessage]:
        payload = json.loads(self.fixture_path.read_text())
        messages = []
        for raw_message in payload:
            attachments = []
            for raw_attachment in raw_message.get("attachments", []):
                content_bytes = b""
                if raw_attachment.get("contentBase64"):
                    content_bytes = base64.b64decode(raw_attachment["contentBase64"])
                elif raw_attachment.get("path"):
                    content_bytes = Path(raw_attachment["path"]).read_bytes()
                attachments.append(
                    MessageAttachment(
                        filename=raw_attachment["filename"],
                        content_bytes=content_bytes,
                        content_type=raw_attachment.get("contentType", "application/octet-stream"),
                    )
                )

            messages.append(
                InboxMessage(
                    id=raw_message["id"],
                    internetMessageId=raw_message.get("internetMessageId", ""),
                    subject=raw_message.get("subject", ""),
                    sender=EmailAddress(**raw_message.get("sender", {})),
                    receivedAt=raw_message.get("receivedAt", ""),
                    body=raw_message.get("body", ""),
                    bodyContentType=raw_message.get("bodyContentType", "text"),
                    attachments=attachments,
                    metadata=raw_message.get("metadata", {}),
                )
            )
        return messages

    def fetch_messages(
        self,
        limit: int,
        subject_filter: Optional[str] = None,
        from_date: Optional[str] = None,
    ) -> List[InboxMessage]:
        messages = self.messages
        if subject_filter:
            lowered = subject_filter.lower()
            messages = [message for message in messages if lowered in message.subject.lower()]

        if from_date:
            try:
                boundary = datetime.strptime(from_date, "%Y-%m-%d")
                messages = [
                    message
                    for message in messages
                    if message.received_at
                    and datetime.strptime(message.received_at[:10], "%Y-%m-%d") >= boundary
                ]
            except ValueError:
                pass

        return messages[:limit]


class GraphInboxClient(InboxClient):
    """Fetch messages and attachments from Microsoft Graph."""

    graph_api_endpoint = "https://graph.microsoft.com/v1.0"

    def __init__(self, config: SourceConfig, retry_config: RetryConfig):
        self.config = config
        self.retry_config = retry_config
        self.access_token = self._authenticate()

    def _authenticate(self) -> str:
        app = msal.ConfidentialClientApplication(
            self.config.client_id,
            authority=f"https://login.microsoftonline.com/{self.config.tenant_id}",
            client_credential=self.config.client_secret,
        )
        result = retry_with_backoff(
            func=lambda: app.acquire_token_for_client(
                scopes=["https://graph.microsoft.com/.default"]
            ),
            attempts=self.retry_config.attempts,
            base_delay_seconds=self.retry_config.base_delay_seconds,
            max_delay_seconds=self.retry_config.max_delay_seconds,
            jitter_ratio=self.retry_config.jitter_ratio,
            retryable_exceptions=(Exception,),
        )
        token = result.get("access_token")
        if not token:
            raise RuntimeError(result.get("error_description", "Graph authentication failed"))
        return token

    def _request(self, endpoint: str, params: Optional[dict] = None) -> dict:
        headers = {"Authorization": f"Bearer {self.access_token}"}
        url = f"{self.graph_api_endpoint}/{endpoint}"
        response = retry_with_backoff(
            func=lambda: requests.get(url, headers=headers, params=params, timeout=30),
            attempts=self.retry_config.attempts,
            base_delay_seconds=self.retry_config.base_delay_seconds,
            max_delay_seconds=self.retry_config.max_delay_seconds,
            jitter_ratio=self.retry_config.jitter_ratio,
            retryable_exceptions=(requests.RequestException,),
        )
        response.raise_for_status()
        return response.json()

    def fetch_messages(
        self,
        limit: int,
        subject_filter: Optional[str] = None,
        from_date: Optional[str] = None,
    ) -> List[InboxMessage]:
        filters = []
        if subject_filter:
            filters.append(f"contains(subject,'{subject_filter}')")
        if from_date:
            filters.append(f"receivedDateTime ge {from_date}")

        params = {
            "$top": limit,
            "$orderby": "receivedDateTime DESC",
            "$select": "id,internetMessageId,subject,from,receivedDateTime,body,hasAttachments",
        }
        if filters:
            params["$filter"] = " and ".join(filters)

        payload = self._request(f"users/{self.config.user_email}/messages", params=params)
        messages = []
        for item in payload.get("value", []):
            attachments = self._fetch_attachments(item["id"]) if item.get("hasAttachments") else []
            sender = item.get("from", {}).get("emailAddress", {})
            body = item.get("body", {})
            messages.append(
                InboxMessage(
                    id=item["id"],
                    internetMessageId=item.get("internetMessageId", ""),
                    subject=item.get("subject", ""),
                    sender=EmailAddress(
                        name=sender.get("name", ""),
                        address=sender.get("address", ""),
                    ),
                    receivedAt=item.get("receivedDateTime", ""),
                    body=body.get("content", ""),
                    bodyContentType=body.get("contentType", "html"),
                    attachments=attachments,
                )
            )
        return messages

    def _fetch_attachments(self, message_id: str) -> List[MessageAttachment]:
        payload = self._request(
            f"users/{self.config.user_email}/messages/{message_id}/attachments"
        )
        attachments = []
        for item in payload.get("value", []):
            if item.get("@odata.type") == "#microsoft.graph.itemAttachment":
                continue
            content_bytes = item.get("contentBytes")
            if not content_bytes:
                continue
            attachments.append(
                MessageAttachment(
                    filename=item.get("name", "attachment.bin"),
                    content_bytes=base64.b64decode(content_bytes),
                    content_type=item.get("contentType", "application/octet-stream"),
                )
            )
        return attachments

