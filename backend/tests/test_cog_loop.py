import pytest
from pathlib import Path
from app.agents.cog_loop import extract_vault_tag_frequencies, build_pattern_context


def test_extract_tag_frequencies_counts_tags(tmp_path):
    (tmp_path / "note1.md").write_text("---\ntags: [python, fastapi]\n---\n", encoding="utf-8")
    (tmp_path / "note2.md").write_text("---\ntags: [python, react]\n---\n", encoding="utf-8")
    (tmp_path / "note3.md").write_text("---\ntags: [react]\n---\n", encoding="utf-8")
    freqs = extract_vault_tag_frequencies(tmp_path)
    assert freqs["python"] == 2
    assert freqs["react"] == 2
    assert freqs["fastapi"] == 1


def test_extract_tag_frequencies_ignores_files_without_frontmatter(tmp_path):
    (tmp_path / "plain.md").write_text("# No frontmatter\n", encoding="utf-8")
    freqs = extract_vault_tag_frequencies(tmp_path)
    assert freqs == {}


def test_build_pattern_context_formats_top_tags():
    freqs = {"python": 10, "react": 7, "fastapi": 5, "sql": 3}
    context = build_pattern_context(freqs, top_n=3)
    assert "python" in context
    assert "react" in context
    assert "fastapi" in context
    assert "sql" not in context  # outside top_n
