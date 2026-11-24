from datetime import date

import pytest

from PySide6.QtWidgets import QApplication

from animevault.media_types import MEDIA_ANIME, MEDIA_MANGA, MEDIA_MANHUA
from animevault.models.anime import Anime
from animevault.models.literature import Literature
from animevault.ui.dashboard_analytics import build_dashboard_data


@pytest.fixture(scope="module")
def qt_app():
    return QApplication.instance() or QApplication([])


def test_dashboard_panel_has_reference_analytics_and_filterable_slicers(qt_app):
    from PySide6.QtCore import Qt
    from animevault.ui.dashboard_analytics import DashboardPanel

    anime = Anime(
        id=None,
        title="Action TV",
        status="completed",
        score=9.0,
        media_type="TV",
        genres=["Action"],
        season_year=2024,
        completed_date="2026-11-20",
    )
    manga = Literature(
        id=None,
        title="Action Manga",
        category=MEDIA_MANGA,
        status="watching",
        format="MANGA",
        genres=["Action"],
        first_read="2026-11-21",
    )
    panel = DashboardPanel()
    panel.resize(1280, 900)
    panel.refresh([anime], [manga])
    qt_app.processEvents()

    assert len(panel._analytics_charts) >= 9
    assert panel._analytics_data["total"] == 2
    assert panel._analytics_charts["media"].chart.kind == "donut"
    assert panel._analytics_charts["formats"].chart.kind == "pie"
    assert panel._analytics_charts["clustered"].chart.kind == "clustered"
    assert panel._analytics_charts["timeline"].chart.kind == "line"
    assert panel._analytics_charts["heatmap"].chart.kind == "heatmap"
    assert panel._analytics_charts["bubbles"].chart.kind == "bubble"
    assert panel._analytics_charts["funnel"].chart.kind == "funnel"

    status_filter = panel._slicers.controls["status"]
    status_filter.setCurrentIndex(status_filter.findData("completed"))
    qt_app.processEvents()
    assert panel._analytics_data["total"] == 1
    assert panel._analytics_data["by_category"][MEDIA_ANIME] == 1
    assert panel._analytics_data["by_category"][MEDIA_MANGA] == 0

    panel.close()


def test_dashboard_reflows_charts_for_requested_desktop_widths(qt_app):
    from animevault.ui.dashboard_analytics import DashboardPanel

    panel = DashboardPanel()
    for width, columns in ((1280, 2), (1366, 2), (1920, 3), (2560, 3)):
        panel.resize(width, 800)
        panel._reflow_analytics()
        assert panel._analytics_grid.columnCount() == columns
    panel.resize(1280, 800)
    panel.show()
    qt_app.processEvents()
    assert panel._content.width() <= panel._scroll.viewport().width() + 1
    for width, expected_columns in ((900, 1), (1280, 2), (1920, 3)):
        panel.resize(width, 800)
        panel._reflow_library_activity()
        actual_columns = max(
            panel._activity_grid.getItemPosition(index)[1]
            for index in range(panel._activity_grid.count())
        ) + 1
        assert actual_columns == expected_columns
    panel.close()


def test_dashboard_navigation_uses_the_react_web_surface(qt_app, migrated_database, monkeypatch):
    from animevault.ui.main_window import MainWindow

    window = MainWindow()
    window.resize(1280, 720)
    calls = []
    monkeypatch.setattr(window._web_view.page(), "runJavaScript", lambda script: calls.append(script))
    window._show_dashboard()
    qt_app.processEvents()
    assert window._dashboard is None
    assert window._stack.currentIndex() == 0
    assert calls and "animevault:dashboard" in calls[-1]
    window.close()


def test_dashboard_slicers_filter_formats_and_genres(qt_app):
    from animevault.ui.dashboard_analytics import DashboardSlicers

    slicers = DashboardSlicers()
    slicers.set_options(["TV", "MANGA"], ["Action", "Comedy"])
    formats = slicers.controls["media_format"]
    genres = slicers.controls["genre"]
    formats.setCurrentIndex(formats.findData("TV"))
    genres.setCurrentIndex(genres.findData("Action"))
    assert slicers.values()["media_format"] == "TV"
    assert slicers.values()["genre"] == "Action"


def test_chart_widget_renders_empty_state_and_all_chart_kinds(qt_app):
    from PySide6.QtCore import QPoint, Qt
    from PySide6.QtGui import QImage, QPainter
    from animevault.ui.dashboard_analytics import DashboardChart, build_dashboard_data

    data = build_dashboard_data(
        [Anime(id=None, title="A", status="watching", genres=["Action"], last_watched="2026-11-20")],
        [Literature(id=None, title="L", category=MEDIA_MANGA, status="completed", genres=["Action"], completed_date="2026-11-21")],
    )
    for kind in ("bar", "tiers", "years", "clustered", "funnel", "pie", "donut", "line", "heatmap", "bubble"):
        chart = DashboardChart(kind)
        chart.resize(420, 220)
        chart.set_data(data)
        image = QImage(chart.size(), QImage.Format.Format_ARGB32)
        image.fill(Qt.GlobalColor.transparent)
        painter = QPainter(image)
        chart.render(painter, QPoint(0, 0))
        painter.end()
        assert not image.isNull()

    chart = DashboardChart("line")
    chart.resize(420, 220)
    chart.set_data(build_dashboard_data([], []))
    image = QImage(chart.size(), QImage.Format.Format_ARGB32)
    image.fill(Qt.GlobalColor.transparent)
    painter = QPainter(image)
    chart.render(painter, QPoint(0, 0))
    painter.end()
    assert not image.isNull()



def test_empty_library_has_complete_zero_filled_breakdowns():
    data = build_dashboard_data([], [])

    assert data["total"] == 0
    assert data["by_category"] == {
        MEDIA_ANIME: 0,
        MEDIA_MANGA: 0,
        "manhwa": 0,
        MEDIA_MANHUA: 0,
    }
    assert all(count == 0 for count in data["status_counts"].values())
    assert data["genres"] == {}
    assert data["timeline"] == {}
    assert data["average_score"] is None


def test_filters_and_chart_values_use_only_matching_library_records():
    anime = Anime(
        id=None,
        title="Action show",
        status="watching",
        score=8.0,
        media_type="TV",
        genres=["Action", "Adventure"],
        episodes=24,
        episodes_watched=12,
        last_watched="2026-11-20",
    )
    manga = Literature(
        id=None,
        title="Action manga",
        category=MEDIA_MANGA,
        status="completed",
        format="MANGA",
        genres=["Action"],
        chapters=60,
        chapters_read=60,
        completed_date="2026-11-21",
    )
    other = Literature(
        id=None,
        title="Comedy manhua",
        category=MEDIA_MANHUA,
        status="plan_to_watch",
        format="MANHUA",
        genres=["Comedy"],
    )

    data = build_dashboard_data(
        [anime], [manga, other], category=MEDIA_MANGA, genre="Action"
    )

    assert data["total"] == 1
    assert data["by_category"][MEDIA_MANGA] == 1
    assert data["by_category"][MEDIA_ANIME] == 0
    assert data["status_counts"]["completed"] == 1
    assert data["genres"] == {"Action": 1}
    assert data["formats"] == {"MANGA": 1}
    assert data["funnel"]["plan_to_watch"] == 0
    assert data["funnel"]["completed"] == 1
    assert data["chapters_read"] == 60
    assert data["average_score"] is None


def test_activity_timeline_and_heatmap_use_recorded_personal_dates_only():
    anime = Anime(
        id=None,
        title="Dated show",
        status="completed",
        last_watched="2025-03-04",
        completed_date="2025-03-05",
    )
    undated = Anime(id=None, title="No history", status="watching")

    data = build_dashboard_data([anime, undated], [], today=date(2025, 3, 6))

    assert data["timeline"] == {"2025-03": 2}
    assert data["heatmap"] == {(2025, 3): 2}
    assert data["total"] == 2


def test_activity_window_excludes_undated_or_stale_records_without_inventing_dates():
    recent = Literature(
        id=None,
        title="Recent",
        category=MEDIA_MANGA,
        status="watching",
        last_read="2026-11-02",
    )
    stale = Anime(id=None, title="Old", status="completed", completed_date="2024-01-01")
    undated = Literature(
        id=None, title="Unknown date", category=MEDIA_MANGA, status="watching"
    )

    data = build_dashboard_data(
        [stale], [recent, undated], activity_window="12m", today=date(2026, 11, 23)
    )

    assert data["total"] == 1
    assert data["by_category"][MEDIA_MANGA] == 1
    assert data["timeline"] == {"2026-11": 1}
