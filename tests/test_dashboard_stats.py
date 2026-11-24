from datetime import datetime

from animevault.ui.dashboard_stats import build_dashboard, norm_media, norm_status


def test_unknown_status_and_media_are_not_relabelled_as_valid_values():
    assert norm_status("corrupt-state") == "unknown"
    assert norm_media("corrupt-media") == "unknown"
    data = build_dashboard([{"id": 1, "media_type": "corrupt-media", "status": "corrupt-state"}], now=datetime(2026, 1, 1))
    assert data["kpis"]["total"] == 1
    assert sum(row["count"] for row in data["media"]) == 1
    assert sum(row["count"] for row in data["status"]) == 1


def test_null_scores_and_totals_remain_unavailable_and_filter_options_are_real():
    data = build_dashboard([{"id": 7, "title": "Actual", "media_type": "anime", "status": "completed", "score": None,
                            "progress": None, "total": None, "genres": ["Action", "Action"]}], now=datetime(2026, 1, 1))
    assert data["kpis"]["avgScore"] is None
    assert data["kpis"]["ratedCount"] == 0
    assert data["kpis"]["episodes"] == [0, 0]
    assert data["genres"] == [{"label": "Action", "count": 1, "media": "anime"}]
    assert data["options"]["genre"] == [{"value": "Action", "label": "Action"}]
