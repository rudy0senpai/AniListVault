"""Background workers: provider search and bounded bulk enrichment.

One enrichment coordinator serves every media category — anime, manga,
manhwa and manhua — so there is a single chunking, caching and
progress-reporting path rather than one per type.
"""

from __future__ import annotations

import datetime
import logging
from typing import Optional

from PySide6.QtCore import QThread, Signal

from animevault.media_types import is_literature
from animevault.models.anime import Anime
from animevault.models.literature import Literature
from animevault.services.enrichment import merge_metadata_into_anime, pick_best_match
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


class BulkEnrichmentWorker(QThread):
    """Processes a mixed list of anime + literature in bounded chunks."""

    progress = Signal(int, int, str, dict)
    enrichment_finished = Signal(dict)

    def __init__(self, items: list, refresh_all: bool = False, parent=None) -> None:
        super().__init__(parent)
        self._items = list(items)
        self._refresh_all = refresh_all
        self._is_cancelled = False
        self._search_service: Optional[SearchService] = None
        self._literature_service = None

    def cancel(self) -> None:
        self._is_cancelled = True

    # ── Helpers ────────────────────────────────────────────────────

    @staticmethod
    def _anime_needs(item: Anime) -> bool:
        return not (item.synopsis and item.anilist_id and item.poster_path)

    @staticmethod
    def _literature_needs(item: Literature) -> bool:
        return not (item.synopsis and item.anilist_id and item.cover_path)

    def _get_services(self):
        """Lazily construct providers so a failure cannot kill the worker."""
        if self._search_service is None:
            try:
                self._search_service = SearchService()
            except Exception as exc:
                logger.warning("Could not build anime search service: %s", exc)
                self._search_service = False
        if self._literature_service is None:
            try:
                from animevault.services.literature_search import (
                    LiteratureSearchService,
                )

                self._literature_service = LiteratureSearchService()
            except Exception as exc:
                logger.warning("Could not build literature service: %s", exc)
                self._literature_service = False
        return self._search_service, self._literature_service

    # ── Main loop ──────────────────────────────────────────────────

    def run(self) -> None:
        total = len(self._items)
        stats = {
            "processed": 0,
            "updated": 0,
            "cached": 0,
            "failed": 0,
            "posters": 0,
        }

        if total == 0:
            self.enrichment_finished.emit(stats)
            return

        for index, item in enumerate(self._items, start=1):
            if self._is_cancelled:
                break

            try:
                literature = is_literature(getattr(item, "category", "")) or isinstance(
                    item, Literature
                )
                needs = (
                    self._literature_needs(item)
                    if literature
                    else self._anime_needs(item)
                )

                if not self._refresh_all and not needs:
                    stats["cached"] += 1
                    stats["processed"] += 1
                    self.progress.emit(
                        index, total, f"Skipped (complete): {item.title}", stats
                    )
                    continue

                message = (
                    self._enrich_literature(item, stats)
                    if literature
                    else self._enrich_anime(item, stats)
                )
                stats["processed"] += 1
                self.progress.emit(index, total, message, stats)

            except Exception as exc:
                logger.warning("Enrichment error for %s: %s", item.title, exc)
                stats["failed"] += 1
                stats["processed"] += 1
                self.progress.emit(index, total, f"Error: {item.title}", stats)

        self.enrichment_finished.emit(stats)

    # ── Per-category enrichment ────────────────────────────────────

    def _enrich_anime(self, anime: Anime, stats: dict) -> str:
        service, _ = self._get_services()
        if not service:
            stats["failed"] += 1
            return f"No provider available: {anime.title}"

        results = service.search(anime.title, limit=5)
        best = pick_best_match(
            anime.title, results, anilist_id=anime.anilist_id, mal_id=anime.mal_id
        )
        if best is None:
            stats["failed"] += 1
            return f"No match: {anime.title}"

        merge_metadata_into_anime(anime, best)
        if best.poster_url and not anime.poster_path:
            local = download_poster(best.poster_url)
            if local:
                anime.poster_path = local
                stats["posters"] += 1
        anime.save()
        stats["updated"] += 1
        return f"Updated: {anime.title}"

    def _enrich_literature(self, item: Literature, stats: dict) -> str:
        _, service = self._get_services()
        if not service:
            stats["failed"] += 1
            return f"No provider available: {item.title}"

        results = service.search(item.title, limit=5)
        if not results:
            stats["failed"] += 1
            return f"No match: {item.title}"

        best = results[0]
        changed = False

        # Fill blanks only — never destroy data already on the record.
        def _fill(attr, value):
            nonlocal changed
            if value and not getattr(item, attr):
                setattr(item, attr, value)
                changed = True

        _fill("synopsis", best.synopsis)
        _fill("format", best.format)
        _fill("pub_status", best.pub_status)
        _fill("origin_country", best.origin_country)
        _fill("started_at", best.started_at)
        _fill("ended_at", best.ended_at)
        _fill("cover_url", best.cover_url)
        if not item.chapters and best.chapters:
            item.chapters = best.chapters
            changed = True
        if not item.volumes and best.volumes:
            item.volumes = best.volumes
            changed = True
        if not item.genres and best.genres:
            item.genres = list(best.genres)
            changed = True
        if not item.authors and best.authors:
            item.authors = list(best.authors)
            changed = True
        if not item.artists and best.artists:
            item.artists = list(best.artists)
            changed = True
        if item.anilist_id is None and best.anilist_id is not None:
            item.anilist_id = best.anilist_id
            changed = True

        # The provider tells us the category; trust it over our guess.
        if best.category and item.category != best.category:
            item.category = best.category
            changed = True

        if best.cover_url and not item.cover_path:
            local = download_poster(best.cover_url)
            if local:
                item.cover_path = local
                stats["posters"] += 1

        if changed:
            item.metadata_fetched_at = datetime.datetime.now(
                datetime.timezone.utc
            ).isoformat()
            item.source_provider = best.source_provider or item.source_provider
            item.save()
            stats["updated"] += 1
            return f"Updated: {item.title}"

        stats["cached"] += 1
        return f"Already complete: {item.title}"