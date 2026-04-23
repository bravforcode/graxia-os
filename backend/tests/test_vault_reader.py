from app.integrations.obsidian import parse_frontmatter, extract_status_from_note, scan_changed_opportunity_files


def test_parse_frontmatter_returns_dict(tmp_path):
    note = tmp_path / "OPP-123.md"
    note.write_text(
        "---\nstatus: won\nscore: 0.9\ntags: [opportunity]\n---\n# Title\n",
        encoding="utf-8"
    )
    result = parse_frontmatter(note)
    assert result == {"status": "won", "score": 0.9, "tags": ["opportunity"]}


def test_parse_frontmatter_returns_empty_for_no_frontmatter(tmp_path):
    note = tmp_path / "plain.md"
    note.write_text("# Just a title\nNo frontmatter here.", encoding="utf-8")
    result = parse_frontmatter(note)
    assert result == {}


def test_extract_status_reads_status_field(tmp_path):
    note = tmp_path / "OPP-456.md"
    note.write_text("---\nstatus: submitted\n---\n", encoding="utf-8")
    status = extract_status_from_note(note)
    assert status == "submitted"


def test_extract_status_returns_none_when_missing(tmp_path):
    note = tmp_path / "OPP-789.md"
    note.write_text("---\ntags: [x]\n---\n", encoding="utf-8")
    status = extract_status_from_note(note)
    assert status is None


def test_scan_changed_opportunity_files_returns_list(tmp_path):
    """Test that scan_changed_opportunity_files finds recently modified opportunity files."""
    # Create vault structure
    opps_dir = tmp_path / "Operations" / "Opportunities"
    opps_dir.mkdir(parents=True, exist_ok=True)

    # Create an opportunity file with status
    note = opps_dir / "OPP-12345678-1234-1234-1234-123456789abc.md"
    note.write_text(
        "---\nstatus: accepted\nscore: 0.85\n---\n# Test Opportunity\n",
        encoding="utf-8"
    )

    # Scan for recently modified files
    result = scan_changed_opportunity_files(tmp_path, since_minutes=1)

    assert len(result) == 1
    assert result[0]["status"] == "accepted"
    assert "mtime" in result[0]
    assert result[0]["file_path"] == note


def test_scan_changed_opportunity_files_returns_empty_for_old_files(tmp_path):
    """Test that scan_changed_opportunity_files ignores old files."""
    import time

    # Create vault structure
    opps_dir = tmp_path / "Operations" / "Opportunities"
    opps_dir.mkdir(parents=True, exist_ok=True)

    # Create an opportunity file
    note = opps_dir / "OPP-87654321-4321-4321-4321-abcdef123456.md"
    note.write_text(
        "---\nstatus: waiting\n---\n# Old Opportunity\n",
        encoding="utf-8"
    )

    # Set the file's modification time to 2 hours ago
    old_time = time.time() - (2 * 60 * 60)
    import os
    os.utime(note, (old_time, old_time))

    # Scan with 35-minute window (default)
    result = scan_changed_opportunity_files(tmp_path, since_minutes=35)

    # Should not find the old file
    assert len(result) == 0
