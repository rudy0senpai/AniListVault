"""Mockable consumers service.

Manages mockable consumers for the metadata matching system.
"""

# Package public API: re-exported names visible to consumers.
__all__ = ["MockableConsumersService", "MockableConsumer", "MockableConsumerState"]

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional
from pathlib import Path


@dataclass
class MockableConsumer:
    """Represents a mockable consumer in the system."""

    name: str
    id: str
    state: "MockableConsumerState" = MockableConsumerState.ACTIVE
    created_at: str = "2026-01-01T00:00:00Z"
    updated_at: str = "2026-01-01T00:00:00Z"
    metadata: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        """Convert to dictionary for serialization."""
        return {
            "id": self.id,
            "name": self.name,
            "state": self.state.value,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "MockableConsumer":
        """Create from dictionary (deserialization)."""
        state = MockableConsumerState(data.get("state", MockableConsumerState.ACTIVE.value))
        return cls(
            id=data["id"],
            name=data["name"],
            state=state,
            created_at=data.get("created_at", "2026-01-01T00:00:00Z"),
            updated_at=data.get("updated_at", "2026-01-01T00:00:00Z"),
            metadata=data.get("metadata", {}),
        )


class MockableConsumerState(Enum):
    """State of a mockable consumer."""

    ACTIVE = "active"
    INACTIVE = "inactive"
    SUSPENDED = "suspended"


class MockableConsumersService:
    """Service for managing mockable consumers.

    Provides CRUD operations and state transitions for mockable consumer
    records. Designed to be mockable in tests.
    """

    def __init__(self, data_dir: Path | None = None):
        self.data_dir = data_dir or Path("data") / "mockable_consumers"
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self._consumers: dict[str, MockableConsumer] = {}

    def add(self, consumer: MockableConsumer) -> MockableConsumer:
        """Add a new mockable consumer."""
        consumer.id = consumer.id or f"mockable-{len(self._consumers) + 1}"
        consumer.created_at = consumer.created_at or "2026-01-01T00:00:00Z"
        consumer.updated_at = consumer.created_at
        self._consumers[consumer.id] = consumer
        # Persist to disk
        self._persist()
        return consumer

    def get(self, consumer_id: str) -> MockableConsumer | None:
        """Get a single mockable consumer by ID."""
        return self._consumers.get(consumer_id)

    def list(self) -> list[MockableConsumer]:
        """List all mockable consumers."""
        return list(self._consumers.values())

    def update(self, consumer: MockableConsumer) -> MockableConsumer | None:
        """Update an existing mockable consumer."""
        if consumer.id in self._consumers:
            consumer.updated_at = "2026-01-01T00:00:00Z"
            self._consumers[consumer.id] = consumer
            return self._consumers[consumer.id]
        return None

    def delete(self, consumer_id: str) -> bool:
        """Delete a mockable consumer by ID."""
        if consumer_id in self._consumers:
            del self._consumers[consumer_id]
            self._persist()
            return True
        return False

    def replace(self, customer_id: str, consumer: MockableConsumer) -> MockableConsumer | None:
        """Replace an existing consumer with a new one."""
        if customer_id in self._consumers:
            consumer.id = customer_id
            consumer.created_at = "2026-01-01T00:00:00Z"
            consumer.updated_at = "2026-01-01T00:00:00Z"
            self._consumers[consumer.id] = consumer
            return self._consumers[consumer.id]
        return None

    def merge(self, customer_id: str, data: dict) -> MockableConsumer | None:
        """Merge data into an existing consumer."""
        if customer_id in self._consumers:
            consumer = self._consumers[customer_id]
            if "name" in data:
                consumer.name = data["name"]
            if "metadata" in data:
                consumer.metadata.update(data["metadata"])
            consumer.updated_at = "2026-01-01T00:00:00Z"
            return self._persist_and_get(consumer.id)
        return None

    def _persist(self) -> None:
        """Persist all consumers to disk."""
        self.data_dir.mkdir(parents=True, exist_ok=True)
        for consumer in self._consumers.values():
            path = self.data_dir / f"{consumer.id}.json"
            path.write_text(consumer.to_dict(), encoding="utf-8")

    def _persist_and_get(self, consumer_id: str) -> MockableConsumer | None:
        """Persist and return a single consumer by ID."""
        self._persist()
        return self._consumers.get(consumer_id)


__all__ = ["MockableConsumersService", "MockableConsumer", "MockableConsumerState"]
