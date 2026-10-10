"""Tree identity, traversal, state and resumability for bulk imports."""

from animevault.media_types import MEDIA_ANIME, MEDIA_MANGA
from animevault.services.import_tree import FetchScheduler, ImportTree, NodeState
from animevault.services.providers.base import ProviderError


import threading
import time


def test_scheduler_respects_bounded_metadata_concurrency():
    scheduler = FetchScheduler(metadata_workers=3, poster_workers=2)
    lock = threading.Lock()
    active = 0
    maximum = 0

    def task(value):
        nonlocal active, maximum
        with lock:
            active += 1
            maximum = max(maximum, active)
        time.sleep(0.02)
        with lock:
            active -= 1
        return value * 2

    results = list(scheduler.map(range(12), task))
    assert maximum == 3
    assert len(results) == 12
    assert all(error is None and result == node * 2 for node, result, error in results)


class Item:
    def __init__(self, title, category=MEDIA_ANIME, anilist_id=None, mal_id=None):
        self.title = title
        self.category = category
        self.anilist_id = anilist_id
        self.mal_id = mal_id


def test_scheduler_retries_transient_failures_but_not_permanent_errors():
    scheduler = FetchScheduler(metadata_workers=1, poster_workers=1)
    attempts = {"transient": 0, "permanent": 0}

    def transient(_value):
        attempts["transient"] += 1
        if attempts["transient"] == 1:
            raise ProviderError("temporary", retryable=True)
        return "ok"

    def permanent(_value):
        attempts["permanent"] += 1
        raise ProviderError("not allowed", retryable=False)

    node = ImportTree().add_item(Item("Transient", MEDIA_ANIME, anilist_id=999))
    permanent_node = ImportTree().add_item(Item("Permanent", MEDIA_ANIME, anilist_id=998))
    transient_result = list(scheduler.map([node], transient))
    permanent_result = list(scheduler.map([permanent_node], permanent))

    assert transient_result[0][1:] == ("ok", None)
    assert attempts["transient"] == 2 and node.retry_count == 1
    assert permanent_result[0][2].retryable is False
    assert attempts["permanent"] == 1


def test_tree_groups_entries_and_deduplicates_provider_identity():
    tree = ImportTree.from_items([
        Item("A", anilist_id=123),
        Item("renamed A", anilist_id=123),
        Item("B", category=MEDIA_MANGA, anilist_id=456),
    ])

    entries = list(tree.iter_entries())
    assert len(entries) == 2
    assert tree.root.parent is None
    assert entries[0].parent.parent is tree.root
    assert entries[0].parent.media_type == MEDIA_ANIME
    assert entries[1].parent.media_type == MEDIA_MANGA
    assert tree.find(entries[0].stable_id) is entries[0]


def test_tree_persists_and_restores_incomplete_task_state(tmp_path):
    tree = ImportTree.from_items([Item("A", anilist_id=123)])
    entry = next(tree.iter_entries())
    entry.metadata_state = NodeState.COMPLETED
    entry.poster_state = NodeState.FAILED
    entry.retry_count = 2
    entry.error = "poster temporarily unavailable"

    path = tree.save(tmp_path / "job.json")
    restored = ImportTree.load(path)
    resumed = restored.find(entry.stable_id)

    assert resumed.state == NodeState.PENDING
    assert resumed.metadata_state == NodeState.COMPLETED
    assert resumed.poster_state == NodeState.FAILED
    assert resumed.retry_count == 2
    assert resumed.error == "poster temporarily unavailable"
    assert restored.incomplete_nodes() == [resumed]


def test_tree_progress_counts_entry_task_states():
    tree = ImportTree.from_items([Item("A"), Item("B", category=MEDIA_MANGA)])
    entries = list(tree.iter_entries())
    entries[0].metadata_state = NodeState.COMPLETED
    entries[0].poster_state = NodeState.COMPLETED
    entries[0].state = NodeState.COMPLETED
    entries[1].state = NodeState.FAILED

    progress = tree.progress()
    assert progress["total"] == 2
    assert progress["completed"] == 1
    assert progress["failed"] == 1
    assert progress["metadata_completed"] == 1
    assert progress["poster_completed"] == 1
