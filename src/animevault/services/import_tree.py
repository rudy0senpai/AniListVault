"""Serializable tree model for resumable bulk metadata imports.

The tree stores compact identifiers and task states only; downloaded image
bytes remain in the poster cache and entry records retain their existing
library objects.
"""

from __future__ import annotations

import json
import os
import random
import re
import unicodedata
import uuid
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import Iterator
from concurrent.futures import ThreadPoolExecutor, as_completed
from threading import Event

from animevault.media_types import (
    MEDIA_ANIME,
    MEDIA_MANGA,
    MEDIA_MANHWA,
    MEDIA_MANHUA,
    normalize_category,
)


class NodeState(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    RETRY_WAIT = "retry_wait"
    CANCELLED = "cancelled"


@dataclass
class ImportNode:
    """Root, media branch, or import entry in the task tree."""

    stable_id: str
    title: str
    media_type: str
    state: NodeState = NodeState.PENDING
    parent: ImportNode | None = field(default=None, repr=False, compare=False)
    children: list[ImportNode] = field(default_factory=list, repr=False, compare=False)
    metadata_state: NodeState = NodeState.PENDING
    poster_state: NodeState = NodeState.PENDING
    validation_state: NodeState = NodeState.PENDING
    persistence_state: NodeState = NodeState.PENDING
    external_ids: dict[str, str] = field(default_factory=dict)
    retry_count: int = 0
    error: str = ""
    poster_path: str = ""

    def add_child(self, node: ImportNode) -> None:
        node.parent = self
        self.children.append(node)


@dataclass
class EntryNode(ImportNode):
    """A library item and its independently tracked import task states."""


class FetchScheduler:
    """Run network tasks concurrently with fixed, API-safe worker bounds."""

    def __init__(self, metadata_workers: int = 5, poster_workers: int = 10):
        if metadata_workers < 1 or poster_workers < 1:
            raise ValueError("Worker limits must be positive")
        self.metadata_workers = metadata_workers
        self.poster_workers = poster_workers

    def map(self, nodes, task, *, kind: str = "metadata", cancel_event: Event | None = None):
        """Yield task results, retrying only bounded transient metadata errors."""
        nodes = list(nodes)
        if cancel_event is not None and cancel_event.is_set():
            for node in nodes:
                if isinstance(node, EntryNode):
                    node.state = NodeState.CANCELLED
                yield node, None, None
            return
        workers = self.metadata_workers if kind == "metadata" else self.poster_workers
        max_retries = 2 if kind == "metadata" else 0
        with ThreadPoolExecutor(max_workers=workers, thread_name_prefix=f"av-{kind}") as pool:
            pending = {pool.submit(task, node): (node, 0) for node in nodes}
            while pending:
                for future in as_completed(tuple(pending)):
                    node, attempt = pending.pop(future)
                    try:
                        result = future.result()
                    except Exception as exc:
                        retryable = bool(getattr(exc, "retryable", False))
                        if retryable and attempt < max_retries and not (
                            cancel_event is not None and cancel_event.is_set()
                        ):
                            node.retry_count += 1
                            node.state = NodeState.RETRY_WAIT
                            delay = min(8.0, 0.5 * (2**attempt)) * random.uniform(0.8, 1.2)
                            cancelled = cancel_event.wait(delay) if cancel_event else False
                            if not cancelled:
                                node.state = NodeState.RUNNING
                                pending[pool.submit(task, node)] = (node, attempt + 1)
                                continue
                            node.state = NodeState.CANCELLED
                        yield node, None, exc
                    else:
                        yield node, result, None
                    if cancel_event is not None and cancel_event.is_set():
                        for waiting in pending:
                            waiting.cancel()
                        return


class ImportTree:
    """Rooted import tree with stable lookup, traversal and JSON checkpoints."""

    MEDIA_TYPES = (MEDIA_ANIME, MEDIA_MANGA, MEDIA_MANHWA, MEDIA_MANHUA)
    JOBS_DIR = Path(os.environ.get("APPDATA", Path.home() / ".local")) / "AnimeVault" / "import_jobs"

    def __init__(self, root: ImportNode | None = None):
        self.root = root or ImportNode(
            stable_id=str(uuid.uuid4()), title="Bulk import", media_type="root"
        )
        self._branches: dict[str, ImportNode] = {}
        self._index: dict[str, EntryNode] = {}
        for branch in self.root.children:
            self._branches[branch.media_type] = branch
            for entry in branch.children:
                self._index[entry.stable_id] = entry

    @classmethod
    def from_items(cls, items: list) -> ImportTree:
        tree = cls()
        for item in items:
            tree.add_item(item)
        return tree

    @staticmethod
    def _identity(media_type: str, title: str, external_ids: dict[str, str]) -> str:
        for provider, key in (
            ("anilist", "anilist_id"), ("mal", "mal_id"),
            ("kitsu", "kitsu_id"), ("tmdb", "tmdb_id"),
        ):
            if external_ids.get(key):
                return f"{media_type}:{provider}:{external_ids[key]}"
        normalized = unicodedata.normalize("NFKC", title).casefold()
        normalized = re.sub(r"\s+", " ", normalized).strip()
        return f"{media_type}:title:{normalized}"

    def add_item(self, item) -> EntryNode:
        raw_type = getattr(item, "category", "")
        media_type = normalize_category(raw_type) if raw_type else MEDIA_ANIME
        if media_type not in self.MEDIA_TYPES:
            media_type = MEDIA_ANIME
        title = str(getattr(item, "title", "") or "Untitled").strip()
        external_ids = {
            name: str(value)
            for name in ("anilist_id", "mal_id", "kitsu_id", "tmdb_id")
            if (value := getattr(item, f"{name}", None)) not in (None, "")
        }
        stable_id = self._identity(media_type, title, external_ids)
        existing = self._index.get(stable_id)
        if existing is not None:
            for key, value in external_ids.items():
                existing.external_ids.setdefault(key, value)
            return existing
        branch = self._branches.get(media_type)
        if branch is None:
            branch = ImportNode(
                stable_id=f"{self.root.stable_id}:{media_type}",
                title=media_type.title(), media_type=media_type,
            )
            self.root.add_child(branch)
            self._branches[media_type] = branch
        entry = EntryNode(
            stable_id=stable_id, title=title, media_type=media_type,
            external_ids=external_ids,
        )
        branch.add_child(entry)
        self._index[stable_id] = entry
        return entry

    def iter_entries(self) -> Iterator[EntryNode]:
        yield from self._index.values()

    def find(self, stable_id: str) -> EntryNode | None:
        return self._index.get(stable_id)

    def incomplete_nodes(self) -> list[EntryNode]:
        return [node for node in self.iter_entries() if node.state != NodeState.COMPLETED]

    def progress(self) -> dict[str, int]:
        entries = list(self.iter_entries())
        return {
            "total": len(entries),
            "completed": sum(node.state == NodeState.COMPLETED for node in entries),
            "failed": sum(node.state == NodeState.FAILED for node in entries),
            "metadata_completed": sum(node.metadata_state == NodeState.COMPLETED for node in entries),
            "poster_completed": sum(node.poster_state == NodeState.COMPLETED for node in entries),
        }

    def save(self, path: str | Path | None = None) -> Path:
        target = Path(path) if path is not None else self.JOBS_DIR / "latest.json"
        target.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "version": 1,
            "root": {"stable_id": self.root.stable_id},
            "entries": [self._entry_dict(entry) for entry in self.iter_entries()],
        }
        temporary = target.with_suffix(target.suffix + ".tmp")
        temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(temporary, target)
        return target

    @staticmethod
    def _entry_dict(entry: EntryNode) -> dict:
        return {
            "stable_id": entry.stable_id,
            "title": entry.title,
            "media_type": entry.media_type,
            "state": entry.state.value,
            "metadata_state": entry.metadata_state.value,
            "poster_state": entry.poster_state.value,
            "validation_state": entry.validation_state.value,
            "persistence_state": entry.persistence_state.value,
            "external_ids": entry.external_ids,
            "retry_count": entry.retry_count,
            "error": entry.error,
            "poster_path": entry.poster_path,
        }

    @classmethod
    def load(cls, path: str | Path) -> ImportTree:
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
        if payload.get("version") != 1:
            raise ValueError("Unsupported import job version")
        root = ImportNode(
            stable_id=str(payload["root"]["stable_id"]),
            title="Bulk import", media_type="root",
        )
        tree = cls(root)
        for raw in payload.get("entries", []):
            media_type = raw["media_type"]
            branch = tree._branches.get(media_type)
            if branch is None:
                branch = ImportNode(
                    stable_id=f"{root.stable_id}:{media_type}",
                    title=media_type.title(), media_type=media_type,
                )
                root.add_child(branch)
                tree._branches[media_type] = branch
            entry = EntryNode(
                stable_id=raw["stable_id"], title=raw["title"], media_type=media_type,
                state=NodeState(raw.get("state", NodeState.PENDING.value)),
                metadata_state=NodeState(raw.get("metadata_state", NodeState.PENDING.value)),
                poster_state=NodeState(raw.get("poster_state", NodeState.PENDING.value)),
                validation_state=NodeState(raw.get("validation_state", NodeState.PENDING.value)),
                persistence_state=NodeState(raw.get("persistence_state", NodeState.PENDING.value)),
                external_ids=dict(raw.get("external_ids", {})),
                retry_count=int(raw.get("retry_count", 0)),
                error=str(raw.get("error", "")),
                poster_path=str(raw.get("poster_path", "")),
            )
            for task_name in (
                "state", "metadata_state", "poster_state",
                "validation_state", "persistence_state",
            ):
                if getattr(entry, task_name) == NodeState.RUNNING:
                    setattr(entry, task_name, NodeState.PENDING)
            branch.add_child(entry)
            tree._index[entry.stable_id] = entry
        return tree
