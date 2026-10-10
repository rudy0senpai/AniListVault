from datetime import datetime, timedelta, timezone

from animevault.models.anime import Anime
from animevault.services.diagnostics import classify_failure, failure_record
from animevault.services.import_tree import ImportTree
from animevault.services.providers.base import ProviderError, parse_retry_after
from animevault.services.workers import BulkEnrichmentWorker


def test_failure_categories_separate_not_found_from_provider_failures():
    assert classify_failure("No matching metadata found") == "no_matching_title"
    assert classify_failure(ProviderError("rate limited", status_code=429)) == "http_429_rate_limited"
    assert classify_failure(ProviderError("server error", status_code=503)) == "http_5xx_server_error"
    assert classify_failure(TimeoutError("timed out")) == "connection_timeout"
    assert classify_failure(ValueError("malformed JSON response")) == "malformed_api_response"


def test_failure_record_scrubs_secret_values():
    item = Anime(id=12, title="Example")
    node = ImportTree.from_items([item]).find("anime:title:example")
    record = failure_record(
        item=item,
        node=node,
        error="request failed api_key=abc123&access_token=xyz789",
        provider="provider-x",
    )
    assert record["item_id"] == 12
    assert record["provider"] == "provider-x"
    assert record["title"] == "Example"
    assert "abc123" not in record["error"]
    assert "xyz789" not in record["error"]
    assert "[REDACTED]" in record["error"]


def test_retry_after_accepts_seconds_and_http_dates():
    assert parse_retry_after("12", 3) == 12
    assert parse_retry_after("invalid", 3) == 3
    soon = (datetime.now(timezone.utc) + timedelta(seconds=30)).strftime("%a, %d %b %Y %H:%M:%S GMT")
    assert 0 <= parse_retry_after(soon, 1) <= 30


def test_no_match_is_unresolved_not_metadata_failure(isolated_database, tmp_path, monkeypatch):
    item = Anime.create(title="Unknown title", status="completed", score=8.0, notes="personal")
    monkeypatch.setattr(BulkEnrichmentWorker, "_fetch_metadata", staticmethod(lambda *_args, **_kwargs: None))
    worker = BulkEnrichmentWorker([item], metadata_workers=1, checkpoint_path=tmp_path / "checkpoint.json")
    outcomes = []
    worker.enrichment_finished.connect(outcomes.append)
    worker.run()
    stats = outcomes[0]
    assert stats["not_found"] == 1
    assert stats["failed"] == 0
    assert stats["failure_details"][0]["category"] == "no_matching_title"
    saved = Anime.find_by_id(item.id)
    assert (saved.status, saved.score, saved.notes) == ("completed", 8.0, "personal")
