import sqlite3
from pathlib import Path


def test_backup_copies_database_without_modifying_source(tmp_path, monkeypatch):
    from animevault.services import backup_service

    source = tmp_path / "library.db"
    with sqlite3.connect(source) as conn:
        conn.execute("CREATE TABLE sentinel (value TEXT)")
        conn.execute("INSERT INTO sentinel VALUES ('keep')")

    backup_dir = tmp_path / "backups"
    monkeypatch.setattr(backup_service, "database_path", lambda: source)
    monkeypatch.setattr(backup_service, "BACKUP_DIR", backup_dir)

    backup = backup_service.backup_database()

    assert backup is not None and backup.exists()
    with sqlite3.connect(source) as conn:
        assert conn.execute("SELECT value FROM sentinel").fetchone() == ("keep",)
    with sqlite3.connect(backup) as conn:
        assert conn.execute("SELECT value FROM sentinel").fetchone() == ("keep",)
