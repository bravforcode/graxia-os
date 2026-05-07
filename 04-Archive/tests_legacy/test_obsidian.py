"""
Tests for Obsidian integration
"""
from datetime import datetime
from pathlib import Path
import tempfile

import pytest

from app.integrations.obsidian import ObsidianConnector


@pytest.fixture
def temp_vault():
    """สร้าง temporary vault สำหรับ testing"""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.mark.asyncio
async def test_write_note_creates_file(temp_vault):
    """ทดสอบการเขียนไฟล์ note"""
    connector = ObsidianConnector(vault_path=str(temp_vault))
    
    file_path = await connector.write_note(
        filename="test-note",
        content="# Test Note\n\nThis is a test.",
        frontmatter={"tags": ["test"], "created": "2024-01-01"},
    )
    
    assert file_path.exists()
    assert file_path.name == "test-note.md"
    
    content = file_path.read_text(encoding="utf-8")
    assert "# Test Note" in content
    assert "tags:" in content
    assert "test" in content


@pytest.mark.asyncio
async def test_write_note_with_folder(temp_vault):
    """ทดสอบการเขียนไฟล์ใน subfolder"""
    connector = ObsidianConnector(vault_path=str(temp_vault))
    
    file_path = await connector.write_note(
        filename="subfolder-note",
        content="Content",
        folder="TestFolder",
    )
    
    assert file_path.exists()
    assert "TestFolder" in str(file_path)


@pytest.mark.asyncio
async def test_read_note(temp_vault):
    """ทดสอบการอ่านไฟล์ note"""
    connector = ObsidianConnector(vault_path=str(temp_vault))
    
    await connector.write_note(
        filename="readable-note",
        content="# Readable\n\nContent here.",
    )
    
    content = await connector.read_note("readable-note")
    assert "# Readable" in content
    assert "Content here" in content


@pytest.mark.asyncio
async def test_append_to_note(temp_vault):
    """ทดสอบการเพิ่มเนื้อหาต่อท้าย"""
    connector = ObsidianConnector(vault_path=str(temp_vault))
    
    await connector.write_note(
        filename="appendable-note",
        content="Original content",
    )
    
    await connector.append_to_note(
        filename="appendable-note",
        content="Appended content",
    )
    
    content = await connector.read_note("appendable-note")
    assert "Original content" in content
    assert "Appended content" in content


@pytest.mark.asyncio
async def test_list_notes(temp_vault):
    """ทดสอบการแสดงรายการไฟล์"""
    connector = ObsidianConnector(vault_path=str(temp_vault))
    
    await connector.write_note("note1", "Content 1")
    await connector.write_note("note2", "Content 2")
    await connector.write_note("note3", "Content 3")
    
    notes = await connector.list_notes()
    assert len(notes) == 3


@pytest.mark.asyncio
async def test_create_daily_note(temp_vault):
    """ทดสอบการสร้าง daily note"""
    connector = ObsidianConnector(vault_path=str(temp_vault))
    
    test_date = datetime(2024, 1, 15)
    file_path = await connector.create_daily_note(date=test_date)
    
    assert file_path.exists()
    assert "2024-01-15" in file_path.name
    
    content = file_path.read_text(encoding="utf-8")
    assert "Today's Focus" in content
    assert "Tasks" in content


@pytest.mark.asyncio
async def test_log_opportunity(temp_vault):
    """ทดสอบการบันทึก opportunity"""
    connector = ObsidianConnector(vault_path=str(temp_vault))
    
    opportunity = {
        "id": "test-123",
        "title": "Test Opportunity",
        "source": "devpost",
        "url": "https://example.com",
        "score": 85,
        "description": "Test description",
    }
    
    file_path = await connector.log_opportunity(opportunity)
    
    assert file_path.exists()
    assert "OPP-test-123" in file_path.name
    
    content = file_path.read_text(encoding="utf-8")
    assert "Test Opportunity" in content
    assert "devpost" in content
    assert "85" in content


@pytest.mark.asyncio
async def test_log_submission(temp_vault):
    """ทดสอบการบันทึก submission"""
    connector = ObsidianConnector(vault_path=str(temp_vault))
    
    submission = {
        "id": "sub-456",
        "title": "Test Submission",
        "opportunity_id": "opp-123",
        "status": "sent",
        "proposal_text": "This is my proposal",
    }
    
    file_path = await connector.log_submission(submission)
    
    assert file_path.exists()
    assert "SUB-sub-456" in file_path.name
    
    content = file_path.read_text(encoding="utf-8")
    assert "Test Submission" in content
    assert "This is my proposal" in content


@pytest.mark.asyncio
async def test_create_contact_note(temp_vault):
    """ทดสอบการสร้าง contact note"""
    connector = ObsidianConnector(vault_path=str(temp_vault))
    
    contact = {
        "id": "contact-789",
        "name": "John Doe",
        "email": "john@example.com",
        "company": "Example Corp",
        "role": "CTO",
    }
    
    file_path = await connector.create_contact_note(contact)
    
    assert file_path.exists()
    assert "John-Doe" in file_path.name
    
    content = file_path.read_text(encoding="utf-8")
    assert "John Doe" in content
    assert "john@example.com" in content
    assert "Example Corp" in content


@pytest.mark.asyncio
async def test_create_weekly_review(temp_vault):
    """ทดสอบการสร้าง weekly review"""
    connector = ObsidianConnector(vault_path=str(temp_vault))
    
    week_start = datetime(2024, 1, 15)
    file_path = await connector.create_weekly_review(week_start)
    
    assert file_path.exists()
    assert "Week-2024" in file_path.name
    
    content = file_path.read_text(encoding="utf-8")
    assert "Weekly Review" in content
    assert "Metrics" in content
    assert "Learnings" in content
