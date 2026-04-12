"""
Tests for Google Workspace integration.
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, timezone

from app.core.google_workspace import GoogleWorkspaceClient


@pytest.fixture
def mock_credentials():
    """Mock Google credentials."""
    with patch('app.core.google_workspace.Credentials') as mock_creds:
        mock_creds.return_value.valid = True
        mock_creds.return_value.expired = False
        yield mock_creds


@pytest.fixture
def mock_gmail_service():
    """Mock Gmail service."""
    mock_service = MagicMock()
    mock_service.users().messages().list().execute.return_value = {
        'messages': [
            {'id': 'msg1', 'threadId': 'thread1'},
            {'id': 'msg2', 'threadId': 'thread2'}
        ]
    }
    return mock_service


@pytest.mark.asyncio
async def test_list_messages(mock_credentials, mock_gmail_service):
    """Test listing Gmail messages."""
    with patch('app.core.google_workspace.build', return_value=mock_gmail_service):
        with patch('app.core.google_workspace.settings') as mock_settings:
            mock_settings.GOOGLE_CLIENT_ID = "test_id"
            mock_settings.GOOGLE_CLIENT_SECRET = "test_secret"
            mock_settings.GOOGLE_REFRESH_TOKEN = "test_token"
            
            client = GoogleWorkspaceClient()
            messages = await client.list_messages(max_results=10)
            
            assert len(messages) == 2
            assert messages[0]['id'] == 'msg1'


@pytest.mark.asyncio
async def test_get_message(mock_credentials, mock_gmail_service):
    """Test getting single Gmail message."""
    mock_gmail_service.users().messages().get().execute.return_value = {
        'id': 'msg1',
        'payload': {
            'headers': [
                {'name': 'Subject', 'value': 'Test Subject'},
                {'name': 'From', 'value': 'test@example.com'}
            ]
        }
    }
    
    with patch('app.core.google_workspace.build', return_value=mock_gmail_service):
        with patch('app.core.google_workspace.settings') as mock_settings:
            mock_settings.GOOGLE_CLIENT_ID = "test_id"
            mock_settings.GOOGLE_CLIENT_SECRET = "test_secret"
            mock_settings.GOOGLE_REFRESH_TOKEN = "test_token"
            
            client = GoogleWorkspaceClient()
            message = await client.get_message('msg1')
            
            assert message is not None
            assert message['id'] == 'msg1'


@pytest.mark.asyncio
async def test_send_message(mock_credentials, mock_gmail_service):
    """Test sending Gmail message."""
    mock_gmail_service.users().messages().send().execute.return_value = {
        'id': 'sent_msg1'
    }
    
    with patch('app.core.google_workspace.build', return_value=mock_gmail_service):
        with patch('app.core.google_workspace.settings') as mock_settings:
            mock_settings.GOOGLE_CLIENT_ID = "test_id"
            mock_settings.GOOGLE_CLIENT_SECRET = "test_secret"
            mock_settings.GOOGLE_REFRESH_TOKEN = "test_token"
            
            client = GoogleWorkspaceClient()
            message_id = await client.send_message(
                to="recipient@example.com",
                subject="Test",
                body="Test body"
            )
            
            assert message_id == 'sent_msg1'


@pytest.mark.asyncio
async def test_health_check(mock_credentials, mock_gmail_service):
    """Test Google Workspace health check."""
    mock_gmail_service.users().getProfile().execute.return_value = {
        'emailAddress': 'test@example.com'
    }
    
    with patch('app.core.google_workspace.build', return_value=mock_gmail_service):
        with patch('app.core.google_workspace.settings') as mock_settings:
            mock_settings.GOOGLE_CLIENT_ID = "test_id"
            mock_settings.GOOGLE_CLIENT_SECRET = "test_secret"
            mock_settings.GOOGLE_REFRESH_TOKEN = "test_token"
            
            client = GoogleWorkspaceClient()
            health = await client.health_check()
            
            assert health['gmail'] == 'healthy'
            assert health['credentials_valid'] is True
            assert health['email_address'] == 'test@example.com'


@pytest.mark.asyncio
async def test_client_without_credentials():
    """Test client initialization without credentials."""
    with patch('app.core.google_workspace.settings') as mock_settings:
        mock_settings.GOOGLE_CLIENT_ID = None
        mock_settings.GOOGLE_CLIENT_SECRET = None
        mock_settings.GOOGLE_REFRESH_TOKEN = None
        
        client = GoogleWorkspaceClient()
        
        assert client.gmail_service is None
        assert client.calendar_service is None
