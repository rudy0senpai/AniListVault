"""Optional local AI (Ollama) metadata normalization layer.

Strictly non-authoritative: only cleans/normalizes synopsis formatting or
genre tags.  Never invents dates, episodes, IDs, or studios.
If Ollama is not running, all operations gracefully pass through unchanged.
"""

from __future__ import annotations

import json
import logging
import os
import urllib.error
import urllib.request
from typing import Optional

from animevault.services.providers.base import AnimeMetadata

logger = logging.getLogger(__name__)

_OLLAMA_URL = os.environ.get("ANIMEVAULT_OLLAMA_URL", "http://127.0.0.1:11434")
_OLLAMA_MODEL = os.environ.get("ANIMEVAULT_OLLAMA_MODEL", "llama3.2:latest")


def is_ollama_available(timeout: float = 0.5) -> bool:
    """Quick check if Ollama server is running locally."""
    try:
        req = urllib.request.Request(f"{_OLLAMA_URL}/api/tags")
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status == 200
    except Exception:
        return False


def enhance_metadata_with_ai(meta: AnimeMetadata) -> AnimeMetadata:
    """Optionally clean up synopsis or format metadata if Ollama is running.

    Provider factual values (episodes, dates, IDs, studios) are NEVER altered.
    """
    if not is_ollama_available():
        return meta

    # Example: clean HTML remnants or excessive markdown in synopsis if present
    if meta.synopsis and len(meta.synopsis) > 50:
        try:
            prompt = (
                "Clean and format the following anime synopsis into clear, cohesive paragraphs. "
                "Do NOT add new information or change facts:\n\n" + meta.synopsis[:1500]
            )
            req_body = json.dumps({
                "model": _OLLAMA_MODEL,
                "prompt": prompt,
                "stream": False,
            }).encode("utf-8")
            req = urllib.request.Request(
                f"{_OLLAMA_URL}/api/generate",
                data=req_body,
                headers={"Content-Type": "application/json"},
            )
            with urllib.request.urlopen(req, timeout=5.0) as resp:
                result = json.loads(resp.read().decode("utf-8"))
                cleaned = (result.get("response") or "").strip()
                if cleaned and len(cleaned) > 20:
                    meta.synopsis = cleaned
        except Exception as exc:
            logger.debug("AI enhancement skipped: %s", exc)

    return meta
