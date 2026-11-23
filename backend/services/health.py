"""Health service for the AnimeVault API."""

from __future__ import annotations


def health_payload(database_path):
    return {
        "status": "ok",
        "service": "animevault-backend",
        "database_path": str(database_path),
    }
