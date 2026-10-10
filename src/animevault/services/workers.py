"""Background workers: provider search and bounded bulk enrichment.

One enrichment coordinator serves every media category — anime, manga,
manhwa and manhua — so there is a single chunking, caching and
progress-reporting path rather than one per type.
"""

from __future__ import annotations

import datetime
import logging
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path
from threading import Event, local
from typing import Optional

from PySide6.QtCore import QThread, Signal

from animevault.media_types import is_literature
from animevault.models.anime import Anime
from animevault.models.literature import Literature
from animevault.database import get_connection
from animevault.services.diagnostics import failure_record, sanitize_error
from animevault.services.enrichment import merge_metadata_into_anime, pick_best_match
from animevault.services.import_tree import EntryNode, FetchScheduler, ImportTree, NodeState
from animevault.services.literature_search import calculate_literature_match_score
from animevault.services.poster import download_poster
from animevault.services.providers.base import AnimeMetadata
from animevault.services.search import SearchService

logger = logging.getLogger(__name__)

#: Records processed per chunk.
CHUNK_SIZE = 25


class SearchWorker(QThread):
    """Executes online anime searches in a background thread."""

    results_ready = Signal(list)
    search_error = Signal(str)

    def __init__(self, query: str, search_service: Optional[SearchService] = None, parent=None) -> None:
        super().__init__(parent)
        self._query = query.strip()
        self._service = search_service or SearchService()

    def run(self) -> None:
        if not self._query:
            self.results_ready.emit([])
            return
        try:
            results = self._service.search(self._query)
            self.results_ready.emit(results)
        except Exception as exc:
            logger.exception("Error in SearchWorker for %r", self._query)
            self.search_error.emit(str(exc))


class _BatchNodeTracker:
    """Associates deferred database writes with their owning tree entries."""

    def __init__(self):
        self._nodes = {}
        self._pending_by_node = {}

    def add(self, item, node):
        item_key = id(item)
        if item_key not in self._nodes:
            self._nodes[item_key] = node
            self._pending_by_node[node.stable_id] = self._pending_by_node.get(node.stable_id, 0) + 1

    def pop_batch(self, items):
        ready = {}
        for item in items:
            node = self._nodes.pop(id(item), None)
            if node is not None:
                remaining = self._pending_by_node[node.stable_id] - 1
                if remaining:
                    self._pending_by_node[node.stable_id] = remaining
                else:
                    self._pending_by_node.pop(node.stable_id, None)
                    ready[node.stable_id] = node
        return list(ready.values())


METADATA_WORKERS = 5
POSTER_WORKERS = 10
DATABASE_BATCH_SIZE = 25
PROGRESS_INTERVAL_SECONDS = 0.35
_thread_services = local()


@dataclass(frozen=True)
class _MetadataOutcome:
    metadata: object
    cache_hit: bool


class BulkEnrichmentWorker(QThread):
    """Processes a mixed list of anime + literature in bounded chunks."""

    progress = Signal(int, int, str, dict)
    enrichment_finished = Signal(dict)
    poster_ready = Signal(int, str)

    def __init__(
        self,
        items: list,
        refresh_all: bool = False,
        parent=None,
        *,
        tree: ImportTree | None = None,
        metadata_workers: int = METADATA_WORKERS,
        poster_workers: int = POSTER_WORKERS,
        checkpoint_path: str | Path | None = None,
        resume_from: str | Path | None = None,
    ) -> None:
        super().__init__(parent)
        self._items = list(items)
        self._refresh_all = refresh_all
        self._is_cancelled = False
        self._cancel_event = Event()
        base_tree = ImportTree.from_items(self._items)
        if tree is None and resume_from and Path(resume_from).exists():
            try:
                restored = ImportTree.load(resume_from)
                if {e.stable_id for e in restored.iter_entries()} == {
                    e.stable_id for e in base_tree.iter_entries()
                }:
                    tree = restored
            except (OSError, ValueError, KeyError, TypeError):
                logger.warning("Ignoring unreadable or incompatible import checkpoint")
        self._tree = tree or base_tree
        self._scheduler = FetchScheduler(metadata_workers, poster_workers)
        self._checkpoint_path = Path(checkpoint_path) if checkpoint_path else None

    def cancel(self) -> None:
        self._is_cancelled = True
        self._cancel_event.set()

    # ── Helpers ────────────────────────────────────────────────────

    @staticmethod
    def _anime_needs(item: Anime) -> bool:
        return not (item.synopsis and item.anilist_id)

    @staticmethod
    def _literature_needs(item: Literature) -> bool:
        return not (item.synopsis and item.anilist_id)

    # ── Main loop ──────────────────────────────────────────────────

    def run(self) -> None:
        stats = {
            "total": 0, "total_tasks": 0, "processed": 0, "updated": 0, "cached": 0,
            "skipped_complete": 0, "failed": 0, "not_found": 0,
            "permanently_unresolved": 0,
            "posters": 0, "metadata_completed": 0, "poster_completed": 0,
            "poster_failed": 0, "retry_attempts": 0, "failure_details": [],
            "cancelled": 0,
        }
        node_items: dict[str, list] = {}
        for item in self._items:
            node = self._tree.add_item(item)
            node_items.setdefault(node.stable_id, []).append(item)
        entries = list(self._tree.iter_entries())
        total = len(self._items)
        stats["total"] = total
        stats["unique_titles"] = len(entries)
        if total == 0:
            self.enrichment_finished.emit(stats)
            return
        self._save_checkpoint()

        pending = []
        resume_posters = []
        for node in entries:
            related = node_items.get(node.stable_id, [])
            if not related:
                continue
            if (
                not self._refresh_all
                and node.metadata_state == NodeState.COMPLETED
                and node.persistence_state == NodeState.COMPLETED
                and all(
                    not (self._literature_needs(item) if isinstance(item, Literature) else self._anime_needs(item))
                    for item in related
                )
            ):
                item = related[0]
                poster_path = getattr(item, "poster_path", "") or getattr(item, "cover_path", "")
                poster_url = getattr(item, "poster_url", "") or getattr(item, "cover_url", "")
                if not poster_path and poster_url:
                    node.state = NodeState.RUNNING
                    node.poster_state = NodeState.RUNNING
                    resume_posters.append((node, item, poster_url))
                else:
                    node.state = NodeState.COMPLETED
                    stats["skipped_complete"] += len(related)
                    stats["processed"] += len(related)
                continue
            if not self._refresh_all and all(
                not (self._literature_needs(item) if isinstance(item, Literature) else self._anime_needs(item))
                for item in related
            ):
                node.metadata_state = node.validation_state = NodeState.COMPLETED
                node.persistence_state = NodeState.COMPLETED
                item = related[0]
                poster_path = getattr(item, "poster_path", "") or getattr(item, "cover_path", "")
                poster_url = getattr(item, "poster_url", "") or getattr(item, "cover_url", "")
                if not poster_path and poster_url:
                    node.state = NodeState.RUNNING
                    node.poster_state = NodeState.RUNNING
                    resume_posters.append((node, item, poster_url))
                else:
                    node.state = node.poster_state = NodeState.COMPLETED
                stats["skipped_complete"] += len(related)
                stats["processed"] += len(related)
            else:
                node.state = NodeState.RUNNING
                node.metadata_state = NodeState.RUNNING
                pending.append(node)

        poster_futures = {}
        dirty = []
        last_emit = time.monotonic()

        def persist_batch(force=False):
            nonlocal dirty
            if not dirty or (not force and len(dirty) < DATABASE_BATCH_SIZE):
                return
            batch, dirty = dirty, []
            try:
                for item in batch:
                    item.save(commit=False)
                with get_connection() as conn:
                    conn.commit()
                for node in batch_nodes.pop_batch(batch):
                    node.persistence_state = NodeState.COMPLETED
                    node.state = NodeState.COMPLETED
            except Exception:
                with get_connection() as conn:
                    conn.rollback()
                logger.exception("Bulk metadata batch persistence failed; retrying records individually")
                for item in batch:
                    node = item_nodes.get(id(item))
                    try:
                        item.save()
                        if node:
                            node.persistence_state = NodeState.COMPLETED
                            node.state = NodeState.COMPLETED
                    except Exception as exc:
                        if node:
                            node.persistence_state = node.state = NodeState.FAILED
                            node.error = sanitize_error(exc)
                            self._record_failure(stats, item, node, exc, stage="persistence")
                        stats["failed"] += 1

        item_nodes = {id(item): node for node in entries for item in node_items.get(node.stable_id, [])}
        batch_nodes = _BatchNodeTracker()

        try:
            with ThreadPoolExecutor(
                max_workers=self._scheduler.poster_workers, thread_name_prefix="av-poster"
            ) as poster_pool:
                for node, item, poster_url in resume_posters:
                    poster_futures[poster_pool.submit(download_poster, poster_url)] = node
                for node, result, error in self._scheduler.map(
                    pending,
                    lambda entry: self._fetch_metadata(
                        entry, node_items[entry.stable_id][0], self._refresh_all
                    ),
                    kind="metadata",
                    cancel_event=self._cancel_event,
                ):
                    if self._is_cancelled:
                        node.state = node.metadata_state = NodeState.CANCELLED
                        continue
                    related = node_items[node.stable_id]
                    if isinstance(result, _MetadataOutcome):
                        if result.cache_hit:
                            stats["cached"] += len(related)
                        result = result.metadata
                    if error is not None:
                        self._mark_failed(node, error, stats, related[0])
                    elif result is None:
                        self._mark_not_found(node, stats, related[0])
                    else:
                        try:
                            self._validate_result(related[0], result)
                            for item in related:
                                if isinstance(item, Literature):
                                    changed = self._merge_literature(item, result)
                                else:
                                    merge_metadata_into_anime(item, result)
                                    changed = True
                                if changed:
                                    item_nodes[id(item)] = node
                                    dirty.append(item)
                                    batch_nodes.add(item, node)
                                if result.poster_url if isinstance(result, AnimeMetadata) else result.cover_url:
                                    if not getattr(item, "poster_path", getattr(item, "cover_path", "")):
                                        node.poster_state = NodeState.RUNNING
                            node.metadata_state = NodeState.COMPLETED
                            node.validation_state = NodeState.COMPLETED
                            stats["metadata_completed"] += 1
                            poster_url = getattr(result, "poster_url", "") or getattr(result, "cover_url", "")
                            if poster_url and not any(getattr(item, "poster_path", "") or getattr(item, "cover_path", "") for item in related):
                                poster_futures[poster_pool.submit(download_poster, poster_url)] = node
                            else:
                                node.poster_state = NodeState.COMPLETED
                            if not any(id(item) in {id(x) for x in dirty} for item in related):
                                node.persistence_state = NodeState.COMPLETED
                                node.state = NodeState.COMPLETED
                            stats["updated"] += len(related)
                        except Exception as exc:
                            self._mark_failed(node, exc, stats, related[0])
                    stats["processed"] += len(related)
                    persist_batch()
                    now = time.monotonic()
                    if now - last_emit >= PROGRESS_INTERVAL_SECONDS or stats["processed"] >= total:
                        self._emit_progress(stats, total, node.title)
                        last_emit = now
                    if stats["processed"] % DATABASE_BATCH_SIZE == 0:
                        self._save_checkpoint()

                persist_batch(force=True)
                for future in as_completed(poster_futures):
                    node = poster_futures[future]
                    try:
                        local_path = future.result()
                    except Exception as exc:
                        local_path = None
                        node.error = sanitize_error(exc)
                    related = node_items[node.stable_id]
                    if local_path:
                        for item in related:
                            if isinstance(item, Literature):
                                item.cover_path = local_path
                            else:
                                item.poster_path = local_path
                            item_nodes[id(item)] = node
                            dirty.append(item)
                            batch_nodes.add(item, node)
                            item_id = getattr(item, "id", None)
                            if item_id is not None:
                                self.poster_ready.emit(int(item_id), str(local_path))
                        stats["posters"] += 1
                        node.poster_path = local_path
                    node.poster_state = NodeState.COMPLETED if local_path else NodeState.FAILED
                    if local_path:
                        stats["poster_completed"] += 1
                    else:
                        stats["poster_failed"] += 1
                        node.error = node.error or "Poster download failed or returned invalid image data"
                        node.state = NodeState.FAILED
                        for item in related:
                            self._record_failure(stats, item, node, node.error, stage="poster")
                    persist_batch()
                persist_batch(force=True)
        except Exception as exc:
            safe_error = sanitize_error(exc)
            logger.error("Bulk import scheduler failed: %s", safe_error)
            for node in self._tree.incomplete_nodes():
                if node.state in (NodeState.PENDING, NodeState.RUNNING, NodeState.RETRY_WAIT):
                    node.state = node.metadata_state = NodeState.FAILED
                    node.error = safe_error
                    related = node_items.get(node.stable_id, [])
                    if related:
                        self._mark_failed(node, exc, stats, related[0])
                    else:
                        stats["failed"] += 1

        if self._is_cancelled:
            for node in self._tree.incomplete_nodes():
                if node.state in (NodeState.PENDING, NodeState.RUNNING):
                    node.state = NodeState.CANCELLED
        stats["retry_attempts"] = sum(node.retry_count for node in entries)
        stats["cancelled"] = sum(node.state == NodeState.CANCELLED for node in entries)
        stats["total_tasks"] = len(entries) + len(poster_futures)
        self._save_checkpoint()
        self._emit_progress(stats, total, "Import complete" if not self._is_cancelled else "Import cancelled")
        self.enrichment_finished.emit(stats)

    def _save_checkpoint(self) -> None:
        try:
            self._tree.save(self._checkpoint_path)
        except OSError:
            logger.exception("Could not save import checkpoint")

    def _emit_progress(self, stats: dict, total: int, title: str) -> None:
        self.progress.emit(
            min(stats["processed"], total), total, title, dict(stats)
        )

    @staticmethod
    def _record_failure(stats: dict, item, node: EntryNode, error, *, stage="metadata") -> None:
        stats["failure_details"].append(
            failure_record(
                item=item,
                node=node,
                error=error,
                stage=stage,
                provider=(
                    getattr(error, "provider", "")
                    or getattr(item, "source_provider", "")
                    or "provider-chain"
                ),
            )
        )

    @classmethod
    def _mark_failed(cls, node: EntryNode, error, stats: dict, item=None) -> None:
        safe_error = sanitize_error(error)
        node.error = safe_error
        node.state = node.metadata_state = NodeState.FAILED
        stats["failed"] += 1
        if getattr(error, "retryable", True) is False and getattr(error, "status_code", None) != 404:
            stats["permanently_unresolved"] += 1
        if item is not None:
            cls._record_failure(stats, item, node, error)

    @classmethod
    def _mark_not_found(cls, node: EntryNode, stats: dict, item=None) -> None:
        message = "No matching metadata found"
        node.error = message
        node.state = node.metadata_state = NodeState.FAILED
        stats["not_found"] += 1
        if item is not None:
            cls._record_failure(stats, item, node, message)


    @staticmethod
    def _fetch_metadata(node: EntryNode, item, force_refresh: bool = False):
        """Perform one provider lookup; called only from a scheduler thread."""
        if isinstance(item, Literature):
            from animevault.services.literature_search import LiteratureSearchService

            service = getattr(_thread_services, "literature", None)
            if service is None:
                service = LiteratureSearchService()
                _thread_services.literature = service
            candidates = service.search(item.title, limit=5, force_refresh=force_refresh)
            if not candidates:
                return _MetadataOutcome(None, bool(service.last_cache_hit))
            best = max(candidates, key=lambda meta: calculate_literature_match_score(item.title, meta))
            return _MetadataOutcome(best, bool(service.last_cache_hit))
        service = getattr(_thread_services, "anime", None)
        if service is None:
            service = SearchService()
            _thread_services.anime = service
        candidates = service.search(item.title, limit=5, force_refresh=force_refresh)
        best = pick_best_match(
            item.title, candidates,
            anilist_id=getattr(item, "anilist_id", None),
            mal_id=getattr(item, "mal_id", None),
        )
        return _MetadataOutcome(best, bool(service.last_cache_hit))

    @staticmethod
    def _validate_result(item, result) -> None:
        if isinstance(item, Literature):
            valid_title = any(
                getattr(result, key, "")
                for key in ("title", "title_en", "title_native")
            )
        else:
            valid_title = any(
                getattr(result, key, "")
                for key in ("title", "title_en", "title_romaji", "title_ja")
            )
        if not valid_title:
            raise ValueError("Provider returned metadata without a usable title")

    @staticmethod
    def _merge_literature(item: Literature, best) -> bool:
        changed = False
        def fill(attr, value):
            nonlocal changed
            if value and not getattr(item, attr):
                setattr(item, attr, value)
                changed = True
        for attr in (
            "synopsis", "format", "pub_status", "origin_country",
            "started_at", "ended_at", "cover_url",
        ):
            fill(attr, getattr(best, attr, ""))
        for attr in ("chapters", "volumes"):
            value = getattr(best, attr, 0)
            if value and not getattr(item, attr):
                setattr(item, attr, value)
                changed = True
        for attr in ("genres", "authors", "artists"):
            value = getattr(best, attr, None)
            if value and not getattr(item, attr):
                setattr(item, attr, list(value))
                changed = True
        for attr in ("anilist_id", "kitsu_id", "mal_id"):
            value = getattr(best, attr, None)
            if value is not None and getattr(item, attr, None) is None:
                setattr(item, attr, value)
                changed = True
        if best.category and item.category != best.category:
            item.category = best.category
            changed = True
        if changed:
            item.metadata_fetched_at = datetime.datetime.now(datetime.timezone.utc).isoformat()
            item.source_provider = best.source_provider or item.source_provider
        return changed
