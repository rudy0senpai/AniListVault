"""Integration tests for concurrent, tree-backed metadata enrichment."""

import threading
import time

from animevault.models.anime import Anime
from animevault.services.import_tree import ImportTree, NodeState
from animevault.services.providers.base import AnimeMetadata
from animevault.services.workers import BulkEnrichmentWorker


def test_cancelled_worker_does_not_start_network_tasks(isolated_database, monkeypatch):
    item = Anime.create(title="Not fetched")

    def unexpected_lookup(*_args, **_kwargs):
        raise AssertionError("cancelled job must not dispatch metadata work")

    monkeypatch.setattr(BulkEnrichmentWorker, "_fetch_metadata", staticmethod(unexpected_lookup))
    worker = BulkEnrichmentWorker([item], metadata_workers=1)
    worker.cancel()
    outcomes = []
    worker.enrichment_finished.connect(outcomes.append)
    worker.run()

    assert outcomes[0]["processed"] == 0
    assert next(worker._tree.iter_entries()).state == NodeState.CANCELLED


def test_bulk_worker_resumes_completed_entries_without_repeated_lookup(
    isolated_database, tmp_path, monkeypatch
):
    item = Anime.create(title="Already enriched", synopsis="saved synopsis", anilist_id=77)
    tree = ImportTree.from_items([item])
    entry = next(tree.iter_entries())
    entry.state = entry.metadata_state = entry.validation_state = entry.persistence_state = NodeState.COMPLETED
    checkpoint = tree.save(tmp_path / "resume.json")

    def unexpected_lookup(*_args, **_kwargs):
        raise AssertionError("completed metadata should not be fetched again")

    monkeypatch.setattr(BulkEnrichmentWorker, "_fetch_metadata", staticmethod(unexpected_lookup))
    worker = BulkEnrichmentWorker([item], resume_from=checkpoint, checkpoint_path=checkpoint)
    outcomes = []
    worker.enrichment_finished.connect(outcomes.append)
    worker.run()

    assert outcomes[0]["cached"] == 1
    assert next(worker._tree.iter_entries()).state.value == "completed"


def test_bulk_worker_fetches_concurrently_preserves_personal_data_and_checkpoints(
    isolated_database, tmp_path, monkeypatch
):
    library = [
        Anime.create(
            title=f"Series {i}", status="completed", score=9.0, tier="S",
            notes="keep this note",
        )
        for i in range(8)
    ]
    lock = threading.Lock()
    active = 0
    peak = 0

    def fake_lookup(_node, item, _force_refresh=False):
        nonlocal active, peak
        with lock:
            active += 1
            peak = max(peak, active)
        time.sleep(0.02)
        with lock:
            active -= 1
        return AnimeMetadata(
            title=item.title, synopsis="Fetched synopsis", anilist_id=9000 + int(item.title.split()[-1]),
            source_provider="fake",
        )

    monkeypatch.setattr(BulkEnrichmentWorker, "_fetch_metadata", staticmethod(fake_lookup))
    worker = BulkEnrichmentWorker(
        library, metadata_workers=4, poster_workers=2,
        checkpoint_path=tmp_path / "checkpoint.json",
    )
    outcomes = []
    worker.enrichment_finished.connect(outcomes.append)
    worker.run()

    assert peak == 4
    assert outcomes[0]["updated"] == 8
    assert all(item.synopsis == "Fetched synopsis" for item in library)
    assert all(item.status == "completed" and item.score == 9.0 for item in library)
    assert all(item.tier == "S" and item.notes == "keep this note" for item in library)
    persisted = [Anime.find_by_id(item.id) for item in library]
    assert all(
        item.status == "completed" and item.score == 9.0
        and item.tier == "S" and item.notes == "keep this note"
        and item.synopsis == "Fetched synopsis"
        for item in persisted
    )
    assert all(node.state.value == "completed" for node in worker._tree.iter_entries())
    assert (tmp_path / "checkpoint.json").exists()
