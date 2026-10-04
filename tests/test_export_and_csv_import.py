"""Tests for CSV import, export (CSV/XLSX/SQL) and English-title preference."""

import pytest

from animevault.media_types import MEDIA_ANIME, MEDIA_MANGA, MEDIA_MANHWA


# ── CSV import ───────────────────────────────────────────────────

class TestCsvReader:
    def test_reads_simple_csv(self, tmp_path):
        from animevault.services.importers.csv_importer import read_csv

        path = tmp_path / "a.csv"
        path.write_text("Title,Tier\nNaruto,SSS\n", encoding="utf-8")
        rows = read_csv(path)
        assert rows[0] == ["Title", "Tier"]
        assert rows[1] == ["Naruto", "SSS"]

    def test_handles_bom_and_semicolons(self, tmp_path):
        from animevault.services.importers.csv_importer import read_csv

        path = tmp_path / "b.csv"
        path.write_bytes("Title;Tier\nBerserk;S\n".encode("utf-8-sig"))
        rows = read_csv(path)
        assert rows[1] == ["Berserk", "S"]

    def test_handles_tabs(self, tmp_path):
        from animevault.services.importers.csv_importer import read_csv

        path = tmp_path / "c.tsv"
        path.write_text("Title\tTier\nX\tA\n", encoding="utf-8")
        assert read_csv(path)[1] == ["X", "A"]

    def test_missing_file_raises(self, tmp_path):
        from animevault.services.importers.csv_importer import CsvError, read_csv

        with pytest.raises(CsvError):
            read_csv(tmp_path / "nope.csv")


class TestCsvPreview:
    def test_maps_known_headers(self, tmp_path):
        from animevault.services.importers.csv_importer import preview_csv

        path = tmp_path / "lib.csv"
        path.write_text(
            "Anime Name,Tier,Watch Status,Chapters Read,Notes\n"
            "Berserk,S,completed,374,Great\n"
            "Solo Leveling,SSS,watching,145,Rewatch\n",
            encoding="utf-8",
        )
        pv = preview_csv(path)
        assert pv.ok
        assert pv.total_rows == 2
        assert pv.valid_rows == 2
        assert pv.has_title_column
        assert pv.unmapped_columns == []

    def test_reports_unmapped_columns(self, tmp_path):
        from animevault.services.importers.csv_importer import preview_csv

        path = tmp_path / "u.csv"
        path.write_text("Title,My Tags,Custom Score\nX,a,1\n", encoding="utf-8")
        pv = preview_csv(path)
        assert pv.unmapped_columns == ["My Tags", "Custom Score"]

    def test_literature_category_detected(self, tmp_path):
        from animevault.services.importers.csv_importer import preview_csv

        path = tmp_path / "c.csv"
        path.write_text(
            "Title,Media Type,Chapters\nSolo Leveling,Manhwa,201\n",
            encoding="utf-8",
        )
        pv = preview_csv(path)
        draft = pv.parsed.drafts[0]
        assert draft.is_literature
        assert draft.category == MEDIA_MANHWA
        assert draft.chapters == 201

    def test_anime_row_without_type_is_anime(self, tmp_path):
        from animevault.services.importers.csv_importer import preview_csv

        path = tmp_path / "a.csv"
        path.write_text("Title,Episodes\nOne Piece,1180\n", encoding="utf-8")
        draft = preview_csv(path).parsed.drafts[0]
        assert draft.is_literature is False
        assert draft.category == ""

    def test_empty_file_reports_error(self, tmp_path):
        from animevault.services.importers.csv_importer import preview_csv

        path = tmp_path / "e.csv"
        path.write_text("", encoding="utf-8")
        assert preview_csv(path).ok is False


# ── Export ───────────────────────────────────────────────────────

class TestExport:
    @pytest.fixture
    def library(self, migrated_database):
        from animevault.models.anime import Anime
        from animevault.models.literature import Literature

        Anime.create(
            title="One Piece", episodes=1180, episodes_watched=1090,
            tier="SSS", status="watching", media_type="TV",
            genres=["Action", "Adventure"], anilist_id=21, notes="Keep",
        )
        Literature.create(
            title="Solo Leveling", category=MEDIA_MANHWA, chapters=201,
            chapters_read=145, tier="S", genres=["Action"], anilist_id=105398,
        )
        return True

    def test_collects_both_categories(self, library):
        from animevault.services.importers.exporter import collect_rows

        rows = collect_rows()
        kinds = {r["media_type"] for r in rows}
        assert MEDIA_ANIME in kinds
        assert MEDIA_MANHWA in kinds
        assert len(rows) == 2

    def test_filter_by_category(self, library):
        from animevault.services.importers.exporter import collect_rows

        rows = collect_rows(category=MEDIA_ANIME)
        assert all(r["media_type"] == MEDIA_ANIME for r in rows)

    def test_export_csv_round_trips(self, library, tmp_path):
        import csv

        from animevault.services.importers.exporter import COLUMNS, export_library

        target = tmp_path / "out.csv"
        result = export_library(target, fmt="csv")
        assert result.row_count == 2

        with target.open(encoding="utf-8-sig") as fh:
            rows = list(csv.DictReader(fh))
        assert len(rows) == 2
        titles = {r["Title"] for r in rows}
        assert "One Piece" in titles and "Solo Leveling" in titles
        assert set(rows[0]) == {c for c in COLUMNS} or "Title" in rows[0]

    def test_export_csv_preserves_personal_fields(self, library, tmp_path):
        import csv

        from animevault.services.importers.exporter import export_library

        target = tmp_path / "p.csv"
        export_library(target, fmt="csv")
        with target.open(encoding="utf-8-sig") as fh:
            rows = list(csv.DictReader(fh))
        one_piece = next(r for r in rows if r["Title"] == "One Piece")
        assert one_piece["Tier"] == "SSS"
        assert one_piece["Notes"] == "Keep"
        assert one_piece["Episodes Watched"] == "1090"
        assert one_piece["AniList ID"] == "21"

    def test_export_xlsx_is_readable_back(self, library, tmp_path):
        from animevault.services.importers.exporter import export_library
        from animevault.services.importers.xlsx_preview import preview_xlsx

        target = tmp_path / "out.xlsx"
        export_library(target, fmt="xlsx")
        pv = preview_xlsx(target)
        assert pv.ok
        assert pv.total_rows == 2
        assert pv.valid_rows == 2
        # Literature must be recognised on the way back in.
        kinds = {d.category for d in pv.parsed.drafts}
        assert MEDIA_MANHWA in kinds

    def test_export_sql_includes_schema_and_data(self, library, tmp_path):
        from animevault.services.importers.exporter import export_library

        target = tmp_path / "out.sql"
        export_library(target, fmt="sql")
        sql = target.read_text(encoding="utf-8")
        assert "CREATE TABLE" in sql
        assert "INSERT INTO anime" in sql
        assert "INSERT INTO literature" in sql
        # No dangerous statements.
        assert "ATTACH" not in sql.upper()
        assert "DROP DATABASE" not in sql.upper()

    def test_export_sql_round_trips(self, library, tmp_path):
        """Export, then import into a *different* database."""
        import animevault.database as db_mod
        from animevault.services.importers.exporter import export_library
        from animevault.services.importers.sql_importer import (
            import_sql,
            preview_sql,
        )
        from animevault.migration import run_migrations

        target = tmp_path / "rt.sql"
        export_library(target, fmt="sql")

        pv = preview_sql(target)
        assert pv.ok
        assert "anime" in pv.tables
        assert "literature" in pv.tables

        # Repoint at a clean database so the import is a true round trip.
        had = hasattr(db_mod._local, "conn")
        if had:
            db_mod._local.conn.close()
            del db_mod._local.conn
        fresh = tmp_path / "fresh.db"
        db_mod.set_database_path(fresh)
        db_mod.initialize_database(fresh)
        run_migrations()
        try:
            result = import_sql(target)
            assert result.added == 2
            assert result.invalid == 0
        finally:
            if hasattr(db_mod._local, "conn"):
                db_mod._local.conn.close()
                del db_mod._local.conn

    def test_export_sql_preserves_provider_ids(self, library, tmp_path):
        """Re-importing the dump must not clobber or lose stored data."""
        import animevault.database as db_mod
        from animevault.models.anime import Anime
        from animevault.services.importers.exporter import export_library
        from animevault.services.importers.sql_importer import import_sql

        target = tmp_path / "ids.sql"
        export_library(target, fmt="sql")
        # Importing into the same library is treated as a duplicate merge;
        # the stored record must keep every personal field.
        result = import_sql(target)
        assert result.added == 0
        assert result.duplicates == 2

        one_piece = Anime.find_by_title("One Piece")
        assert one_piece is not None
        assert one_piece.tier == "SSS"
        assert one_piece.episodes_watched == 1090
        assert one_piece.anilist_id == 21

    def test_unsupported_format_raises(self, library, tmp_path):
        from animevault.services.importers.exporter import export_library

        with pytest.raises(ValueError):
            export_library(tmp_path / "x.json", fmt="json")


# ── English title preference ─────────────────────────────────────

class TestEnglishTitlePreference:
    def test_english_preferred_over_romaji(self):
        from animevault.services.providers.literature import LiteratureMetadata

        meta = LiteratureMetadata(
            title="Kusuriya no Hitorigoto",
            title_en="The Apothecary Diaries",
            title_romaji="Kusuriya no Hitorigoto",
            title_native="薬屋のひとりごと",
        )
        assert meta.display_title() == "The Apothecary Diaries"

    def test_romaji_used_when_no_english(self):
        from animevault.services.providers.literature import LiteratureMetadata

        meta = LiteratureMetadata(
            title="berserk", title_en="", title_romaji="berserk",
            title_native="ベルセルク",
        )
        assert meta.display_title() == "berserk"

    def test_native_used_as_last_resort(self):
        from animevault.services.providers.literature import LiteratureMetadata

        meta = LiteratureMetadata(title="", title_en="", title_native="監獄�話")
        assert meta.display_title() == "監獄�話"

    def test_normalizer_prefers_english(self):
        from animevault.services.providers.literature import normalize_literature

        meta = normalize_literature(
            {
                "id": 1,
                "title": {"romaji": "Sinui Tap", "english": "Tower of God", "native": "신의 탑"},
                "countryOfOrigin": "KR",
                "format": "MANGA",
            }
        )
        assert meta.title == "Tower of God"
        assert meta.title_en == "Tower of God"
        assert meta.title_romaji == "Sinui Tap"
        assert meta.title_native == "신의 탑"
        assert meta.display_title() == "Tower of God"

    def test_korean_origin_maps_to_manhwa(self):
        from animevault.services.providers.literature import normalize_literature

        meta = normalize_literature(
            {
                "id": 1,
                "title": {"romaji": "Na Honjaman Level Up", "english": "Solo Leveling", "native": "나 혼자만 레벨업"},
                "countryOfOrigin": "KR",
                "format": "MANGA",
            }
        )
        assert meta.category == MEDIA_MANHWA

class TestXlsxIsValidForExcel:
    """Excel silently "repairs" a workbook whose styles.xml is incomplete.

    The required fonts/fills/borders sections must be present, otherwise
    Excel discards cell text and shows a repair banner.
    """

    def _export(self, tmp_path):
        from animevault.services.importers.exporter import export_library

        from animevault.models.anime import Anime

        Anime.create(
            title="Naruto", title_en="Naruto", episodes=220,
            episodes_watched=220, tier="SS", status="completed",
            media_type="TV", genres=["Action", "Adventure"],
            studios=["Studio Pierrot"], season="FALL", season_year=2002,
        )
        return export_library(tmp_path / "out.xlsx", fmt="xlsx").path

    def test_styles_declares_required_sections(self, migrated_database, tmp_path):
        import zipfile

        path = self._export(tmp_path)
        with zipfile.ZipFile(path) as z:
            styles = z.read("xl/styles.xml").decode("utf-8")
        for tag in ("fonts", "fills", "borders", "cellXfs",
                    "cellStyleXfs", "cellStyles"):
            assert f"<{tag}" in styles, f"styles.xml is missing <{tag}>"

    def test_every_part_is_valid_xml(self, migrated_database, tmp_path):
        import zipfile
        from xml.etree import ElementTree as ET

        path = self._export(tmp_path)
        with zipfile.ZipFile(path) as z:
            for name in z.namelist():
                if name.endswith((".xml", ".rels")):
                    ET.fromstring(z.read(name))  # raises on malformed XML

    def test_text_and_metadata_survive_a_round_trip(self, migrated_database, tmp_path):
        from animevault.services.importers.xlsx_preview import preview_xlsx

        path = self._export(tmp_path)
        preview = preview_xlsx(path)
        assert preview.valid_rows >= 1
        draft = preview.parsed.drafts[0]
        assert draft.title == "Naruto"
        assert draft.tier == "SS"
        assert draft.episodes == 220
        assert "Action" in draft.genres

    def test_csv_carries_the_same_fields(self, migrated_database, tmp_path):
        import csv

        from animevault.services.importers.exporter import export_library

        from animevault.models.anime import Anime

        Anime.create(title="Bleach", episodes=366, tier="A",
                     genres=["Action"], studios=["Studio Pierrot"])
        path = export_library(tmp_path / "out.csv", fmt="csv").path
        with path.open(encoding="utf-8-sig") as handle:
            rows = list(csv.DictReader(handle))
        row = next(r for r in rows if r["Title"] == "Bleach")
        assert row["Episodes"] == "366"
        assert row["Tier"] == "A"
        assert row["Genres"] == "Action"
        assert row["Studios"] == "Studio Pierrot"
        assert row["Media Type"] == "anime"

    def test_sql_export_contains_metadata_table(self, migrated_database, tmp_path):
        from animevault.services.importers.exporter import export_library
        from animevault.services.importers.sql_importer import preview_sql

        from animevault.models.literature import Literature

        Literature.create(title="Solo Leveling", category="manhwa",
                          chapters=201, tier="SSS", authors=["Chugong"])
        path = export_library(tmp_path / "out.sql", fmt="sql").path
        preview = preview_sql(path)
        assert preview.ok
        assert "literature" in preview.tables
        assert "INSERT INTO literature_metadata" in path.read_text(encoding="utf-8")
