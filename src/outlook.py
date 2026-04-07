"""
Outlook API Integration Module
Handles email fetching from Microsoft Outlook using Graph API
"""

import msal
import requests
from typing import List, Dict, Optional
from datetime import datetime


class OutlookClient:
    """Client for interacting with Microsoft Outlook via Graph API"""

    GRAPH_API_ENDPOINT = 'https://graph.microsoft.com/v1.0'

    def __init__(self, config: Dict):
        """
        Initialize Outlook client

        Args:
            config: Dictionary containing Microsoft API credentials
        """
        self.config = config
        self.access_token = None
        self._authenticate()

    def _authenticate(self):
        """Authenticate with Microsoft Graph API using MSAL"""
        app = msal.ConfidentialClientApplication(
            self.config['client_id'],
            authority=f"https://login.microsoftonline.com/{self.config['tenant_id']}",
            client_credential=self.config['client_secret']
        )

        # Get token for Graph API
        result = app.acquire_token_for_client(
            scopes=["https://graph.microsoft.com/.default"]
        )

        if "access_token" in result:
            self.access_token = result['access_token']
        else:
            raise Exception(f"Authentication failed: {result.get('error_description', 'Unknown error')}")

    def _make_request(self, endpoint: str, params: Optional[Dict] = None) -> Dict:
        """Make authenticated request to Graph API"""
        headers = {
            'Authorization': f'Bearer {self.access_token}',
            'Content-Type': 'application/json'
        }

        url = f"{self.GRAPH_API_ENDPOINT}/{endpoint}"
        response = requests.get(url, headers=headers, params=params)
        response.raise_for_status()

        return response.json()

    def fetch_emails(
        self,
        subject_filter: Optional[str] = None,
        from_date: Optional[str] = None,
        limit: int = 10
    ) -> List[Dict]:
        """
        Fetch emails from Outlook

        Args:
            subject_filter: Filter by subject keyword
            from_date: Fetch emails from this date (YYYY-MM-DD)
            limit: Maximum number of emails to fetch

        Returns:
            List of email dictionaries
        """
        user_email = self.config['user_email']
        endpoint = f"users/{user_email}/messages"

        # Build filter query
        filters = []
        if subject_filter:
            filters.append(f"contains(subject, '{subject_filter}')")
        if from_date:
            filters.append(f"receivedDateTime ge {from_date}")

        params = {
            '$top': limit,
            '$orderby': 'receivedDateTime DESC',
            '$select': 'id,subject,from,receivedDateTime,body,hasAttachments'
        }

        if filters:
            params['$filter'] = ' and '.join(filters)

        result = self._make_request(endpoint, params)
        return result.get('value', [])

    def get_email_by_id(self, email_id: str) -> Optional[Dict]:
        """
        Fetch specific email by ID

        Args:
            email_id: The email message ID

        Returns:
            Email dictionary or None
        """
        try:
            user_email = self.config['user_email']
            endpoint = f"users/{user_email}/messages/{email_id}"
            return self._make_request(endpoint)
        except requests.HTTPError as e:
            if e.response.status_code == 404:
                return None
            raise

    def fetch_attachments(self, email_id: str) -> List[Dict]:
        """
        Download attachments for a given email.

        Returns:
            List of dicts with 'filename' and 'data' (bytes) keys.
        """
        import base64
        user_email = self.config['user_email']
        endpoint = f"users/{user_email}/messages/{email_id}/attachments"
        result = self._make_request(endpoint)

        attachments = []
        for att in result.get('value', []):
            if att.get('@odata.type') == '#microsoft.graph.itemAttachment':
                continue  # skip embedded email attachments
            content_bytes = att.get('contentBytes')
            if content_bytes:
                attachments.append({
                    'filename': att.get('name', 'unknown'),
                    'data': base64.b64decode(content_bytes),
                })
        return attachments

    def delete_email(self, email_id: str):
        """Delete a single email by ID."""
        user_email = self.config['user_email']
        url = f"{self.GRAPH_API_ENDPOINT}/users/{user_email}/messages/{email_id}"
        headers = {
            'Authorization': f'Bearer {self.access_token}',
        }
        response = requests.delete(url, headers=headers)
        response.raise_for_status()

    def clear_mailbox(self, limit: int = 100) -> int:
        """Delete all emails in the inbox (up to limit). Returns count deleted."""
        emails = self.fetch_emails(limit=limit)
        for email in emails:
            self.delete_email(email['id'])
        return len(emails)

    def get_email_body(self, email: Dict) -> str:
        """
        Extract email body text

        Args:
            email: Email dictionary from Graph API

        Returns:
            Email body as text
        """
        body = email.get('body', {})
        content = body.get('content', '')
        content_type = body.get('contentType', 'text')

        # If HTML, you might want to strip HTML tags
        # For now, return as-is
        return content
