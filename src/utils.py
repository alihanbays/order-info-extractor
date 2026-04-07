"""
Utility Functions
Helper functions for the application
"""

from datetime import datetime
from typing import Any, Dict
import re


def parse_date(date_string: str) -> datetime:
    """
    Parse date string to datetime object

    Args:
        date_string: Date in various formats

    Returns:
        datetime object
    """
    formats = [
        '%Y-%m-%d',
        '%Y/%m/%d',
        '%d-%m-%Y',
        '%d/%m/%Y',
        '%Y-%m-%dT%H:%M:%S',
        '%Y-%m-%dT%H:%M:%SZ',
    ]

    for fmt in formats:
        try:
            return datetime.strptime(date_string, fmt)
        except ValueError:
            continue

    raise ValueError(f"Unable to parse date: {date_string}")


def clean_html(html_text: str) -> str:
    """
    Remove HTML tags from text

    Args:
        html_text: HTML content

    Returns:
        Plain text
    """
    # Simple HTML tag removal
    clean = re.compile('<.*?>')
    text = re.sub(clean, '', html_text)

    # Remove extra whitespace
    text = re.sub(r'\s+', ' ', text)

    return text.strip()


def format_currency(amount: Any) -> str:
    """
    Format number as currency

    Args:
        amount: Numeric value

    Returns:
        Formatted currency string
    """
    try:
        return f"${float(amount):.2f}"
    except (ValueError, TypeError):
        return str(amount)


def validate_email(email: str) -> bool:
    """
    Validate email address format

    Args:
        email: Email address

    Returns:
        True if valid, False otherwise
    """
    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    return re.match(pattern, email) is not None
