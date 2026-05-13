from __future__ import annotations

import os
from dataclasses import dataclass

from src.core.config import APP_SETTINGS
from src.db.connection import DatabaseConnection
from src.registry.a2a_log_registry import A2ALogRegistry
from src.registry.agent_connection_registry import AgentConnectionRegistry
from src.registry.agent_registry import AgentRegistry
from src.registry.alert_registry import AlertRegistry
from src.registry.approval_registry import ApprovalRegistry
from src.registry.config_registry import ConfigRegistry
from src.registry.device_registry import DeviceRegistry
from src.registry.device_role_registry import DeviceRoleRegistry
from src.registry.event_registry import EventRegistry
from src.registry.insight_registry import InsightRegistry
from src.registry.mission_proposal_registry import MissionProposalRegistry
from src.registry.mission_registry import MissionRegistry
from src.registry.operation_plan_registry import OperationPlanRegistry
from src.registry.policy_registry import PolicyRegistry
from src.registry.proposal_task_registry import ProposalTaskRegistry
from src.registry.report_registry import ReportRegistry
from src.registry.rule_registry import RuleRegistry
from src.registry.sensor_registry import SensorRegistry
from src.registry.task_registry import TaskRegistry
from src.registry.user_registry import UserRegistry
from src.transport.moth_subscriber import MothHealthcheckSubscriber


@dataclass
class RegistryComponents:
    registry: DeviceRegistry
    alert_registry: AlertRegistry
    event_registry: EventRegistry
    a2a_log_registry: A2ALogRegistry
    policy_registry: PolicyRegistry
    user_registry: UserRegistry
    agent_registry: AgentRegistry
    proposal_task_registry: ProposalTaskRegistry
    task_registry: TaskRegistry
    report_registry: ReportRegistry
    rule_registry: RuleRegistry
    config_registry: ConfigRegistry
    sensor_registry: SensorRegistry
    mission_registry: MissionRegistry
    device_role_registry: DeviceRoleRegistry
    operation_plan_registry: OperationPlanRegistry
    insight_registry: InsightRegistry
    approval_registry: ApprovalRegistry
    mission_proposal_registry: MissionProposalRegistry
    agent_connection_registry: AgentConnectionRegistry
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

    user_db_path = ":memory:" if storage_type == "memory" else ".data/users.db"
    agent_db_path = ":memory:" if storage_type == "memory" else ".data/agents.db"
    proposal_task_db_path = ":memory:" if storage_type == "memory" else ".data/proposal_tasks.db"
    task_db_path = ":memory:" if storage_type == "memory" else ".data/tasks.db"
    report_db_path = ":memory:" if storage_type == "memory" else ".data/reports.db"
    rule_db_path = ":memory:" if storage_type == "memory" else ".data/rules.db"
    config_db_path = ":memory:" if storage_type == "memory" else ".data/configs.db"
    sensor_db_path = ":memory:" if storage_type == "memory" else ".data/sensors.db"
    mission_db_path = ":memory:" if storage_type == "memory" else ".data/missions.db"
    device_role_db_path = ":memory:" if storage_type == "memory" else ".data/device_roles.db"
    operation_plan_db_path = ":memory:" if storage_type == "memory" else ".data/operation_plans.db"
    insight_db_path = ":memory:" if storage_type == "memory" else ".data/insights.db"
    approval_db_path = ":memory:" if storage_type == "memory" else ".data/approvals.db"
    mission_proposal_db_path = ":memory:" if storage_type == "memory" else ".data/mission_proposals.db"
    agent_connection_db_path = ":memory:" if storage_type == "memory" else ".data/agent_connections.db"

    user_registry = UserRegistry(db_path=user_db_path)
    agent_registry = AgentRegistry(db_path=agent_db_path)
    proposal_task_registry = ProposalTaskRegistry(db_path=proposal_task_db_path)
    task_registry = TaskRegistry(db_path=task_db_path)
    report_registry = ReportRegistry(db_path=report_db_path)
    rule_registry = RuleRegistry(db_path=rule_db_path)
    config_registry = ConfigRegistry(db_path=config_db_path)
    sensor_registry = SensorRegistry(db_path=sensor_db_path)
    mission_registry = MissionRegistry(db_path=mission_db_path)
    device_role_registry = DeviceRoleRegistry(db_path=device_role_db_path)
    operation_plan_registry = OperationPlanRegistry(db_path=operation_plan_db_path)
    insight_registry = InsightRegistry(db_path=insight_db_path)
    approval_registry = ApprovalRegistry(db_path=approval_db_path)
    mission_proposal_registry = MissionProposalRegistry(db_path=mission_proposal_db_path)
    agent_connection_registry = AgentConnectionRegistry(db_path=agent_connection_db_path)

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
        user_registry=user_registry,
        agent_registry=agent_registry,
        proposal_task_registry=proposal_task_registry,
        task_registry=task_registry,
        report_registry=report_registry,
        rule_registry=rule_registry,
        config_registry=config_registry,
        sensor_registry=sensor_registry,
        mission_registry=mission_registry,
        device_role_registry=device_role_registry,
        operation_plan_registry=operation_plan_registry,
        insight_registry=insight_registry,
        approval_registry=approval_registry,
        mission_proposal_registry=mission_proposal_registry,
        agent_connection_registry=agent_connection_registry,
        moth_subscriber=moth_subscriber,
        storage_type=storage_type,
        db=DatabaseConnection(),
    )


__all__ = ["RegistryComponents", "build_registry_components"]
