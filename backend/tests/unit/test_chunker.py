import pytest
from app.core.chunker import VaultChunker

def test_vault_chunker_basic_split():
    chunker = VaultChunker(window_size=10, overlap=0)
    content = "This is a simple sentence with more than ten words in it to test split."
    chunks = chunker.process_file(content)
    assert len(chunks) >= 2
    assert "simple" in chunks[0].text

def test_vault_chunker_header_split():
    chunker = VaultChunker(window_size=100, overlap=10)
    content = """# Header 1
Content 1 is here.

## Header 2
Content 2 is here.
"""
    chunks = chunker.process_file(content)
    assert len(chunks) == 2
    assert "# Header 1" in chunks[0].text
    assert "## Header 2" in chunks[1].text

def test_vault_chunker_frontmatter_extraction():
    chunker = VaultChunker()
    content = """---
tags: [test, rag]
category: project
---
Body content here.
"""
    chunks = chunker.process_file(content)
    assert chunks[0].metadata["tags"] == ["test", "rag"]
    assert chunks[0].metadata["category"] == "project"
    assert "Body content" in chunks[0].text
