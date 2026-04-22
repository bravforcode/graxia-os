import hashlib
from dataclasses import dataclass
from typing import Any
import yaml

@dataclass
class Chunk:
    text: str
    metadata: dict[str, Any]
    hash: str

class VaultChunker:
    def __init__(self, window_size: int = 512, overlap: int = 64):
        self.window_size = window_size
        self.overlap = overlap

    def process_file(self, content: str, default_metadata: dict[str, Any] | None = None) -> list[Chunk]:
        metadata = default_metadata.copy() if default_metadata else {}
        body = content

        if content.startswith("---"):
            end_idx = content.find("---", 3)
            if end_idx != -1:
                frontmatter_text = content[3:end_idx]
                try:
                    fm = yaml.safe_load(frontmatter_text)
                    if isinstance(fm, dict):
                        for k in ["tags", "category", "date", "project", "project_id"]:
                            if k in fm:
                                metadata[k] = fm[k]
                except yaml.YAMLError:
                    pass
                body = content[end_idx + 3:].strip()

        words = body.split()
        chunks = []
        step = self.window_size - self.overlap
        if step <= 0:
            step = 1

        for i in range(0, max(1, len(words)), step):
            chunk_words = words[i:i + self.window_size]
            chunk_text = " ".join(chunk_words)
            chunk_hash = hashlib.sha256(chunk_text.encode("utf-8")).hexdigest()
            chunks.append(Chunk(text=chunk_text, metadata=metadata, hash=chunk_hash))

            if i + self.window_size >= len(words):
                break

        return chunks
