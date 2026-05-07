import hashlib
import re
from dataclasses import dataclass
from typing import Any

import yaml


@dataclass
class Chunk:
    text: str
    metadata: dict[str, Any]
    hash: str

class VaultChunker:
    """Intelligent Markdown chunker that respects header boundaries and max length."""
    
    def __init__(self, window_size: int = 512, overlap: int = 64):
        self.window_size = window_size
        self.overlap = overlap

    def process_file(self, content: str, default_metadata: dict[str, Any] | None = None) -> list[Chunk]:
        metadata = default_metadata.copy() if default_metadata else {}
        body = content

        # Extract frontmatter
        if content.startswith("---"):
            end_idx = content.find("---", 3)
            if end_idx != -1:
                frontmatter_text = content[3:end_idx]
                try:
                    fm = yaml.safe_load(frontmatter_text)
                    if isinstance(fm, dict):
                        # Filter specific keys to keep metadata clean
                        for k in ["tags", "category", "date", "project", "project_id", "source"]:
                            if k in fm:
                                metadata[k] = fm[k]
                except yaml.YAMLError:
                    pass
                body = content[end_idx + 3:].strip()

        # Initial split by major headers (h1, h2)
        sections = re.split(r'\n(?=# [^#]|## [^#])', body)
        
        chunks = []
        for section in sections:
            if not section.strip():
                continue
                
            # If section is small enough, keep as one chunk
            words = section.split()
            if len(words) <= self.window_size:
                chunk_text = section.strip()
                chunk_hash = hashlib.sha256(chunk_text.encode("utf-8")).hexdigest()
                chunks.append(Chunk(text=chunk_text, metadata=metadata, hash=chunk_hash))
            else:
                # Sub-chunking for long sections
                step = self.window_size - self.overlap
                for i in range(0, len(words), step):
                    chunk_words = words[i:i + self.window_size]
                    chunk_text = " ".join(chunk_words)
                    chunk_hash = hashlib.sha256(chunk_text.encode("utf-8")).hexdigest()
                    chunks.append(Chunk(text=chunk_text, metadata=metadata, hash=chunk_hash))
                    
                    if i + self.window_size >= len(words):
                        break

        return chunks
