"""Shared email sending module — Gmail API with SMTP fallback.

Used by both recovery_dashboard.py and automated_weekly_email.py.
"""

import base64
import json
import logging
import os
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from pathlib import Path

logger = logging.getLogger(__name__)


def send_email(to_address: str, subject: str, html_body: str) -> bool:
    """Send an HTML email. Tries Gmail API first, then SMTP fallback.

    Returns True if sent successfully via either method.
    """
    if _send_via_gmail_api(to_address, subject, html_body):
        return True
    if _send_via_smtp(to_address, subject, html_body):
        return True
    return False


def _send_via_gmail_api(to_address: str, subject: str, html_body: str) -> bool:
    """Send via Gmail API with OAuth credentials from ~/.gmail-mcp/credentials.json."""
    try:
        from google.oauth2.credentials import Credentials
        from google.auth.transport.requests import Request
        from googleapiclient.discovery import build

        creds_path = Path.home() / ".gmail-mcp" / "credentials.json"
        if not creds_path.exists():
            logger.info("No Gmail API credentials found, will try SMTP")
            return False

        with open(creds_path, 'r') as f:
            creds_data = json.load(f)

        token = creds_data.get('access_token') or creds_data.get('token')
        refresh_token = creds_data.get('refresh_token')
        client_id = creds_data.get('client_id')
        client_secret = creds_data.get('client_secret')

        if not token:
            logger.warning("No access token in credentials")
            return False

        credentials = Credentials(
            token=token,
            refresh_token=refresh_token,
            token_uri=creds_data.get('token_uri', 'https://oauth2.googleapis.com/token'),
            client_id=client_id,
            client_secret=client_secret,
        )

        if not credentials.valid and refresh_token and client_id and client_secret:
            logger.info("Refreshing expired credentials...")
            credentials.refresh(Request())

        message = MIMEMultipart('alternative')
        message['to'] = to_address
        message['subject'] = subject
        message.attach(MIMEText(html_body, 'html'))

        raw = base64.urlsafe_b64encode(message.as_bytes()).decode()
        service = build('gmail', 'v1', credentials=credentials)
        result = service.users().messages().send(userId='me', body={'raw': raw}).execute()

        logger.info(f"Email sent via Gmail API! Message ID: {result['id']}")
        return True

    except Exception as e:
        logger.warning(f"Gmail API send failed: {e}")
        return False


def _send_via_smtp(to_address: str, subject: str, html_body: str) -> bool:
    """Send via Gmail SMTP with app password from environment.

    Requires env vars: GMAIL_APP_PASSWORD and (GMAIL_SMTP_USER or GARMIN_EMAIL).
    """
    import smtplib

    smtp_user = os.environ.get('GMAIL_SMTP_USER') or os.environ.get('GARMIN_EMAIL')
    smtp_pass = os.environ.get('GMAIL_APP_PASSWORD')

    if not smtp_user or not smtp_pass:
        logger.error("No SMTP credentials available (set GMAIL_APP_PASSWORD secret)")
        return False

    try:
        message = MIMEMultipart('alternative')
        message['From'] = smtp_user
        message['To'] = to_address
        message['Subject'] = subject
        message.attach(MIMEText(html_body, 'html'))

        with smtplib.SMTP_SSL('smtp.gmail.com', 465) as server:
            server.login(smtp_user, smtp_pass)
            server.send_message(message)

        logger.info(f"Email sent via SMTP to {to_address}")
        return True

    except Exception as e:
        logger.error(f"SMTP send failed: {e}")
        return False