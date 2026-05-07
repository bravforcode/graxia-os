import logging
import os
from datetime import UTC, datetime, timedelta

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential

logger = logging.getLogger(__name__)

OLLAMA_BASE_URL = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434")
MODEL = "nomic-embed-text"

_failures = []
_blocked_until = None

def _is_blocked():
    global _blocked_until, _failures
    now = datetime.now(UTC)
    if _blocked_until and now < _blocked_until:
        return True
    
    _failures = [t for t in _failures if (now - t) < timedelta(seconds=60)]
    if len(_failures) >= 3:
        _blocked_until = now + timedelta(minutes=5)
        logger.warning(f"Ollama embedder failing. Blocked until {_blocked_until}")
        return True
        
    return False

def _record_failure():
    global _failures
    _failures.append(datetime.now(UTC))

@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
async def _do_embed(text: str) -> list[float]:
    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.post(
            f"{OLLAMA_BASE_URL}/api/embeddings",
            json={"model": MODEL, "prompt": text}
        )
        response.raise_for_status()
        data = response.json()
        return data.get("embedding")

async def embed_text_async(text: str) -> list[float] | None:
    if _is_blocked():
        return None
        
    try:
        return await _do_embed(text)
    except Exception as e:
        logger.warning(f"Failed to embed text via Ollama after retries: {e}")
        _record_failure()
        return None

async def embed_batch_async(texts: list[str]) -> list[list[float] | None]:
    # Process sequentially or in small parallel batches to avoid overloading local model
    results = []
    for text in texts:
        results.append(await embed_text_async(text))
    return results

def embed_text(text: str) -> list[float] | None:
    import asyncio
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None
        
    if loop and loop.is_running():
        raise RuntimeError("Use embed_text_async in async context")
    return asyncio.run(embed_text_async(text))
