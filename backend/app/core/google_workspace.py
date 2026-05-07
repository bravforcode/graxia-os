"""
Google Workspace Integration Module

Provides Gmail and Google Calendar integration with OAuth2 authentication.
"""
import base64
import logging
from datetime import UTC, date, datetime, time, timedelta
from typing import Any

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from app.config import settings

logger = logging.getLogger(__name__)


class GoogleWorkspaceClient:
    """
    Google Workspace API client for Gmail and Calendar.
    
    Features:
    - Gmail: list, get, send, search messages
    - Calendar: list, create, update events
    - OAuth2 authentication with refresh token
    - Error handling and retry logic
    """
    
    def __init__(self):
        self.credentials = None
        self.gmail_service = None
        self.calendar_service = None
        self._initialization_attempted = False
        self._initialization_error: str | None = None

    def _has_real_credentials(self) -> bool:
        return settings.HAS_REAL_GOOGLE_WORKSPACE_CREDENTIALS
    
    def _initialize_credentials(self):
        """Initialize OAuth2 credentials from settings."""
        if self._initialization_attempted and (
            self.gmail_service is not None or self.calendar_service is not None
        ):
            return

        self._initialization_attempted = True
        try:
            if not self._has_real_credentials():
                return
            
            self.credentials = Credentials(
                token=None,
                refresh_token=settings.GOOGLE_REFRESH_TOKEN,
                token_uri="https://oauth2.googleapis.com/token",
                client_id=settings.GOOGLE_CLIENT_ID,
                client_secret=settings.GOOGLE_CLIENT_SECRET,
                scopes=(
                    [
                        "https://www.googleapis.com/auth/gmail.readonly",
                        "https://www.googleapis.com/auth/calendar.readonly",
                    ]
                    + (
                        [
                            "https://www.googleapis.com/auth/gmail.send",
                            "https://www.googleapis.com/auth/gmail.modify",
                            "https://www.googleapis.com/auth/calendar.events",
                        ]
                        if settings.GOOGLE_ENABLE_WRITE_SCOPES
                        else []
                    )
                ),
            )
            
            # Refresh token if needed
            if self.credentials.expired or not self.credentials.valid:
                self.credentials.refresh(Request())
            
            # Build services
            self.gmail_service = build('gmail', 'v1', credentials=self.credentials)
            self.calendar_service = build('calendar', 'v3', credentials=self.credentials)
            self._initialization_error = None
            
            logger.info("Google Workspace client initialized successfully")
        except Exception as e:
            self.credentials = None
            self.gmail_service = None
            self.calendar_service = None
            self._initialization_error = str(e)
            logger.warning(f"Google Workspace client initialization failed: {e}")

    def _ensure_initialized(self) -> bool:
        if self.gmail_service or self.calendar_service:
            return True
        if not self._has_real_credentials():
            return False
        self._initialize_credentials()
        return self.gmail_service is not None or self.calendar_service is not None
    
    async def list_messages(
        self,
        max_results: int = 50,
        query: str = "is:unread"
    ) -> list[dict[str, Any]]:
        """
        List Gmail messages.
        
        Args:
            max_results: Maximum number of messages to return
            query: Gmail search query (e.g., "is:unread", "from:example@gmail.com")
        
        Returns:
            List of message metadata dicts
        """
        if not self.gmail_service and not self._ensure_initialized():
            logger.warning("Gmail service not initialized")
            return []
        
        try:
            results = self.gmail_service.users().messages().list(
                userId='me',
                maxResults=max_results,
                q=query
            ).execute()
            
            messages = results.get('messages', [])
            logger.info(f"Listed {len(messages)} Gmail messages")
            return messages
        except HttpError as e:
            logger.error(f"Gmail list messages failed: {e}")
            return []
    
    async def get_message(self, message_id: str) -> dict[str, Any] | None:
        """
        Get full Gmail message by ID.
        
        Args:
            message_id: Gmail message ID
        
        Returns:
            Full message dict or None
        """
        if not self.gmail_service and not self._ensure_initialized():
            return None
        
        try:
            message = self.gmail_service.users().messages().get(
                userId='me',
                id=message_id,
                format='full'
            ).execute()
            
            return message
        except HttpError as e:
            logger.error(f"Gmail get message failed: {e}")
            return None
    
    async def send_message(
        self,
        to: str,
        subject: str,
        body: str,
        reply_to: str | None = None,
        is_html: bool = False,
        extra_headers: dict[str, str] | None = None,
    ) -> str | None:
        """
        Send Gmail message.
        
        Args:
            to: Recipient email
            subject: Email subject
            body: Email body (plain text)
            reply_to: Message ID to reply to (optional)
        
        Returns:
            Sent message ID or None
        """
        if not self.gmail_service and not self._ensure_initialized():
            return None
        
        try:
            from email.mime.text import MIMEText
            
            message = MIMEText(body, "html" if is_html else "plain")
            message['to'] = to
            message['subject'] = subject
            if extra_headers:
                for key, value in extra_headers.items():
                    if key and value:
                        message[key] = value
            
            if reply_to:
                message['In-Reply-To'] = reply_to
                message['References'] = reply_to
            
            raw = base64.urlsafe_b64encode(message.as_bytes()).decode()
            
            sent_message = self.gmail_service.users().messages().send(
                userId='me',
                body={'raw': raw}
            ).execute()
            
            logger.info(f"Sent email to {to}: {subject}")
            return sent_message.get('id')
        except HttpError as e:
            logger.error(f"Gmail send message failed: {e}")
            return None
    
    async def mark_as_read(self, message_id: str) -> bool:
        """Mark Gmail message as read."""
        if not self.gmail_service and not self._ensure_initialized():
            return False
        
        try:
            self.gmail_service.users().messages().modify(
                userId='me',
                id=message_id,
                body={'removeLabelIds': ['UNREAD']}
            ).execute()
            
            return True
        except HttpError as e:
            logger.error(f"Gmail mark as read failed: {e}")
            return False
    
    async def list_calendar_events(
        self,
        max_results: int = 10,
        time_min: datetime | None = None,
        time_max: datetime | None = None
    ) -> list[dict[str, Any]]:
        """
        List Google Calendar events.
        
        Args:
            max_results: Maximum number of events
            time_min: Start time filter
            time_max: End time filter
        
        Returns:
            List of event dicts
        """
        if not self.calendar_service and not self._ensure_initialized():
            return []
        
        try:
            if not time_min:
                time_min = datetime.now(UTC)
            
            events_result = self.calendar_service.events().list(
                calendarId='primary',
                timeMin=time_min.isoformat(),
                timeMax=time_max.isoformat() if time_max else None,
                maxResults=max_results,
                singleEvents=True,
                orderBy='startTime'
            ).execute()
            
            events = events_result.get('items', [])
            logger.info(f"Listed {len(events)} calendar events")
            return events
        except HttpError as e:
            logger.error(f"Calendar list events failed: {e}")
            return []
    
    async def create_calendar_event(
        self,
        summary: str,
        start_time: datetime,
        end_time: datetime,
        description: str | None = None,
        location: str | None = None
    ) -> str | None:
        """
        Create Google Calendar event.
        
        Args:
            summary: Event title
            start_time: Event start time
            end_time: Event end time
            description: Event description
            location: Event location
        
        Returns:
            Event ID or None
        """
        if not self.calendar_service and not self._ensure_initialized():
            return None
        
        try:
            event = {
                'summary': summary,
                'start': {
                    'dateTime': start_time.isoformat(),
                    'timeZone': 'Asia/Bangkok',
                },
                'end': {
                    'dateTime': end_time.isoformat(),
                    'timeZone': 'Asia/Bangkok',
                },
            }
            
            if description:
                event['description'] = description
            if location:
                event['location'] = location
            
            created_event = self.calendar_service.events().insert(
                calendarId='primary',
                body=event
            ).execute()
            
            logger.info(f"Created calendar event: {summary}")
            return created_event.get('id')
        except HttpError as e:
            logger.error(f"Calendar create event failed: {e}")
            return None

    def _headers_to_dict(self, payload: dict[str, Any] | None) -> dict[str, str]:
        headers = payload.get("headers", []) if isinstance(payload, dict) else []
        return {
            str(item.get("name") or ""): str(item.get("value") or "")
            for item in headers
            if isinstance(item, dict)
        }

    def _extract_body_text(self, payload: dict[str, Any] | None) -> str:
        if not isinstance(payload, dict):
            return ""
        body = payload.get("body", {})
        if isinstance(body, dict) and body.get("data"):
            try:
                return base64.urlsafe_b64decode(body["data"]).decode(
                    "utf-8", errors="ignore"
                )
            except Exception:
                return ""
        for part in payload.get("parts", []) or []:
            if not isinstance(part, dict):
                continue
            mime_type = str(part.get("mimeType") or "")
            if mime_type == "text/plain":
                encoded = (part.get("body") or {}).get("data")
                if not encoded:
                    continue
                try:
                    return base64.urlsafe_b64decode(encoded).decode(
                        "utf-8", errors="ignore"
                    )
                except Exception:
                    return ""
        return ""

    async def health(self) -> dict[str, Any]:
        configured = self._has_real_credentials()
        if configured:
            self._ensure_initialized()
        raw_status = await self.health_check()
        gmail_ok = raw_status.get("gmail") == "healthy"
        calendar_ok = raw_status.get("calendar") == "healthy"
        if not configured:
            status = "not_configured"
        elif gmail_ok and calendar_ok:
            status = "ok"
        elif gmail_ok or calendar_ok:
            status = "degraded"
        else:
            status = "error"
        return {
            "status": status,
            "configured": configured,
            **raw_status,
        }

    async def get_gmail_inbox_summary(
        self,
        max_results: int = 10,
    ) -> dict[str, Any]:
        if not self.gmail_service and not self._ensure_initialized():
            configured = self._has_real_credentials()
            return {
                "status": "error" if configured and self._initialization_error else "not_configured",
                "configured": configured,
                "messages": [],
                "unread_count": 0,
                "total_count": 0,
                "issues": (
                    [self._initialization_error]
                    if self._initialization_error
                    else ["Google Workspace Gmail is not configured"]
                ),
            }

        try:
            message_refs = await self.list_messages(
                max_results=max_results,
                query="in:inbox",
            )
            messages: list[dict[str, Any]] = []
            unread_count = 0
            for message_ref in message_refs:
                full_message = await self.get_message(str(message_ref.get("id") or ""))
                if not full_message:
                    continue
                payload = full_message.get("payload", {})
                headers = self._headers_to_dict(payload)
                labels = set(full_message.get("labelIds") or [])
                is_unread = "UNREAD" in labels
                if is_unread:
                    unread_count += 1
                snippet = str(full_message.get("snippet") or "").strip()
                if not snippet:
                    snippet = self._extract_body_text(payload)[:280]
                messages.append(
                    {
                        "id": full_message.get("id"),
                        "thread_id": full_message.get("threadId"),
                        "from": headers.get("From", ""),
                        "subject": headers.get("Subject", "(No Subject)"),
                        "date": headers.get("Date", ""),
                        "snippet": snippet,
                        "unread": is_unread,
                        "labels": sorted(labels),
                    }
                )

            return {
                "status": "ok",
                "configured": True,
                "messages": messages,
                "unread_count": unread_count,
                "total_count": len(messages),
                "issues": [],
            }
        except Exception as e:
            logger.error(f"Gmail inbox summary failed: {e}")
            return {
                "status": "error",
                "configured": True,
                "messages": [],
                "unread_count": 0,
                "total_count": 0,
                "issues": [str(e)],
            }

    async def get_calendar_day_summary(
        self,
        target_date: date,
        max_results: int = 10,
    ) -> dict[str, Any]:
        if not self.calendar_service and not self._ensure_initialized():
            configured = self._has_real_credentials()
            return {
                "status": "error" if configured and self._initialization_error else "not_configured",
                "configured": configured,
                "date": target_date.isoformat(),
                "events": [],
                "issues": (
                    [self._initialization_error]
                    if self._initialization_error
                    else ["Google Workspace Calendar is not configured"]
                ),
            }

        try:
            tz = UTC
            start_of_day = datetime.combine(target_date, time.min, tzinfo=tz)
            end_of_day = start_of_day + timedelta(days=1)
            raw_events = await self.list_calendar_events(
                max_results=max_results,
                time_min=start_of_day,
                time_max=end_of_day,
            )
            events: list[dict[str, Any]] = []
            for event in raw_events:
                start = event.get("start") or {}
                end = event.get("end") or {}
                events.append(
                    {
                        "id": event.get("id"),
                        "summary": event.get("summary", "(No title)"),
                        "description": event.get("description"),
                        "location": event.get("location"),
                        "start": start.get("dateTime") or start.get("date"),
                        "end": end.get("dateTime") or end.get("date"),
                        "attendees": event.get("attendees") or [],
                    }
                )
            return {
                "status": "ok",
                "configured": True,
                "date": target_date.isoformat(),
                "events": events,
                "issues": [],
            }
        except Exception as e:
            logger.error(f"Calendar day summary failed: {e}")
            return {
                "status": "error",
                "configured": True,
                "date": target_date.isoformat(),
                "events": [],
                "issues": [str(e)],
            }

    async def health_check(self) -> dict[str, Any]:
        """Check Google Workspace service health."""
        self._ensure_initialized()
        status = {
            "gmail": "unavailable",
            "calendar": "unavailable",
            "credentials_valid": False
        }
        
        try:
            if self.credentials and self.credentials.valid:
                status["credentials_valid"] = True
            
            if self.gmail_service:
                # Try to get profile
                profile = self.gmail_service.users().getProfile(userId='me').execute()
                if profile:
                    status["gmail"] = "healthy"
                    status["email_address"] = profile.get('emailAddress')
            
            if self.calendar_service:
                # Try to list calendars
                calendars = self.calendar_service.calendarList().list(maxResults=1).execute()
                if calendars:
                    status["calendar"] = "healthy"
        except Exception as e:
            logger.error(f"Google Workspace health check failed: {e}")
            status["error"] = str(e)

        if self._initialization_error and "error" not in status:
            status["error"] = self._initialization_error
        
        return status


# Global client instance
google_workspace = GoogleWorkspaceClient()
