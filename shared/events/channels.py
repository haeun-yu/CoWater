"""Redis pub/sub 채널 이름 상수."""

# Moth Bridge → Core / Agents
PLATFORM_REPORT = "platform.report.{platform_id}"  # PlatformReport JSON
PLATFORM_REPORT_PATTERN = "platform.report.*"

# Core → Frontend (WebSocket 브릿지)
PLATFORM_STATUS_CHANGED = "platform.status.changed"

# Agents → Core / Frontend
ALERT_CREATED = "alert.created.{severity}"  # severity: info|warning|critical
ALERT_CREATED_PATTERN = "alert.created.*"
ALERT_UPDATED = "alert.updated.{alert_id}"
ALERT_UPDATED_PATTERN = "alert.updated.*"

# Core API → Agent Runtime
AGENT_COMMAND = "agent.command.{agent_id}"  # enable|disable|set_level|set_config

# Agent Runtime → Core
AGENT_HEALTH = "agent.health.{agent_id}"


def platform_report_channel(platform_id: str) -> str:
    return f"platform.report.{platform_id}"


def platform_report_pattern() -> str:
    return PLATFORM_REPORT_PATTERN


def alert_created_channel(severity: str) -> str:
    return f"alert.created.{severity}"


def alert_created_pattern() -> str:
    return ALERT_CREATED_PATTERN


def alert_updated_channel(alert_id: str) -> str:
    return f"alert.updated.{alert_id}"


def alert_updated_pattern() -> str:
    return ALERT_UPDATED_PATTERN


def agent_command_channel(agent_id: str) -> str:
    return f"agent.command.{agent_id}"


def agent_health_channel(agent_id: str) -> str:
    return f"agent.health.{agent_id}"
