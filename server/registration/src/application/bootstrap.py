from __future__ import annotations

import os
from dataclasses import dataclass

from src.core.config import APP_SETTINGS
from src.db.connection import DatabaseConnection
from src.registry.a2a_log_registry import A2ALogRegistry
from src.registry.alert_registry import AlertRegistry
from src.registry.device_registry import DeviceRegistry
from src.registry.domain_registry import DomainRegistry
from src.registry.event_registry import EventRegistry
from src.registry.policy_registry import PolicyRegistry
from src.transport.moth_subscriber import MothHealthcheckSubscriber


@dataclass
class RegistryComponents:
    registry: DeviceRegistry
    alert_registry: AlertRegistry
    event_registry: EventRegistry
    a2a_log_registry: A2ALogRegistry
    policy_registry: PolicyRegistry
    domain_registry: DomainRegistry
    moth_subscriber: MothHealthcheckSubscriber
    storage_type: str
    db: DatabaseConnection


def build_registry_components() -> RegistryComponents:
    storage_type = os.getenv("COWATER_STORAGE", "sqlite").lower()
    alert_db_path = ":memory:" if storage_type == "memory" else ".data/alerts.db"
    event_db_path = ":memory:" if storage_type == "memory" else ".data/events.db"
    a2a_log_db_path = ":memory:" if storage_type == "memory" else ".data/a2a_logs.db"

    registry = DeviceRegistry(
        secret_key=APP_SETTINGS["secret_key"],
        host=APP_SETTINGS["server"]["host"],
        port=APP_SETTINGS["server"]["port"],
        ping_endpoint=APP_SETTINGS["server"]["ping_endpoint"],
        agent_scheme=APP_SETTINGS["agent"]["scheme"],
        agent_host=APP_SETTINGS["agent"]["host"],
        agent_port=APP_SETTINGS["agent"]["port"],
        agent_path_prefix=APP_SETTINGS["agent"]["path_prefix"],
        agent_command_scheme=APP_SETTINGS["agent"]["command_scheme"],
        agent_command_path_prefix=APP_SETTINGS["agent"]["command_path_prefix"],
        healthcheck_interval_seconds=APP_SETTINGS["healthcheck"]["interval_seconds"],
        healthcheck_timeout_seconds=APP_SETTINGS["healthcheck"]["timeout_seconds"],
        healthcheck_timeout_by_device_type=APP_SETTINGS["healthcheck"].get("timeout_by_device_type", {}),
        healthcheck_topic_template=APP_SETTINGS["moth"]["healthcheck_topic_template"],
        telemetry_topic_template=APP_SETTINGS["moth"]["telemetry_topic_template"],
    )

    alert_registry = AlertRegistry(db_path=alert_db_path)
    event_registry = EventRegistry(db_path=event_db_path)
    a2a_log_registry = A2ALogRegistry(db_path=a2a_log_db_path)
    policy_registry = PolicyRegistry()
    domain_registry = DomainRegistry()

    moth_subscriber = MothHealthcheckSubscriber(
        registry=registry,
        moth_server_url=APP_SETTINGS["moth"]["server_url"],
    )

    return RegistryComponents(
        registry=registry,
        alert_registry=alert_registry,
        event_registry=event_registry,
        a2a_log_registry=a2a_log_registry,
        policy_registry=policy_registry,
        domain_registry=domain_registry,
        moth_subscriber=moth_subscriber,
        storage_type=storage_type,
        db=domain_registry.db,
    )


__all__ = ["RegistryComponents", "build_registry_components"]
