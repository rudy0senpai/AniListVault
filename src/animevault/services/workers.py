"""Background Qt threads for responsive search and bounded bulk enrichment."""

from __future__ import annotations

import logging
from typing import Optional

from PySide6.QtCore import QThread, Signal

from animevault.models.anime import Anime
from animevault.services.enrichment import merge_metadata_into_anime, pick_best_match
from animevault.services.poster import download_poster
from animevault.services.providers.base import AnimeMetadata
from animevault.services.search import SearchService

logger = logging.getLogger(__name__)


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
    """Processes library-wide enrichment in bounded chunks."""

    progress = Signal(int, int, str, dict)
    enrichment_finished = Signal(dict)

    CHUNK_SIZE = 25

    def __init__(self, anime_list: list[Anime], refresh_all: bool = False, parent=None) -> None:
        super().__init__(parent)
        self._anime_list = anime_list
        self._refresh_all = refresh_all
        self._is_cancelled = False
        self._search_service = SearchService()

    def cancel(self) -> None:
        self._is_cancelled = True

    def run(self) -> None:
        total = len(self._anime_list)
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

        for idx, anime in enumerate(self._anime_list, start=1):
            if self._is_cancelled:
                break

            # Skip if anime already has complete metadata unless refresh_all is True
            if not self._refresh_all and anime.synopsis and anime.genres and anime.anilist_id and anime.poster_path:
                stats["cached"] += 1
                stats["processed"] += 1
                self.progress.emit(idx, total, f"Skipped (complete): {anime.title}", stats)
                continue

            try:
                # Search for match
                results = self._search_service.search(anime.title, limit=5)
                best = pick_best_match(
                    anime.title,
                    results,
                    anilist_id=anime.anilist_id,
                    mal_id=anime.mal_id,
                )

                if best:
                    merge_metadata_into_anime(anime, best)

                    # Download poster if needed
                    if best.poster_url and not anime.poster_path:
                        local_poster = download_poster(best.poster_url)
                        if local_poster:
                            anime.poster_path = local_poster
                            stats["posters"] += 1

                    anime.save()
                    stats["updated"] += 1
                    msg = f"Updated: {anime.title}"
                else:
                    stats["failed"] += 1
                    msg = f"No match: {anime.title}"

            except Exception as exc:
                logger.warning("Enrichment error for %s: %s", anime.title, exc)
                stats["failed"] += 1
                msg = f"Error: {anime.title}"

            stats["processed"] += 1
            self.progress.emit(idx, total, msg, stats)

        self.enrichment_finished.emit(stats)
