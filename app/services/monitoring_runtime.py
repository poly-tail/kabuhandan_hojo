"""Shared runtime objects for Phase 2+ monitoring features."""

from __future__ import annotations

from functools import lru_cache

from kabuhandan_hojo.core.config import Settings as MonitoringSettings
from kabuhandan_hojo.core.container import ServiceContainer, build_container


@lru_cache(maxsize=1)
def get_monitoring_settings() -> MonitoringSettings:
    """Return cached monitoring settings."""

    return MonitoringSettings()


@lru_cache(maxsize=1)
def get_monitoring_container() -> ServiceContainer:
    """Build shared monitoring services."""

    return build_container(get_monitoring_settings())
