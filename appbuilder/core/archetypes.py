"""Shared application archetype definitions."""

from __future__ import annotations

from enum import Enum


class AppArchetype(str, Enum):
    """Supported application archetypes."""

    CRUD = "crud"
    PASSTHROUGH_ROUTER = "passthrough-router"
    KAFKA_INTEGRATION = "kafka-integration"


DEFAULT_APP_ARCHETYPE = AppArchetype.CRUD
