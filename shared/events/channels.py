"""Redis pub/sub 채널 이름 상수."""

# Moth Bridge → Core / Agents
PLATFORM_REPORT = "platform.report.{platform_id}"   # PlatformReport JSON

# Core → Frontend (WebSocket 브릿지)
PLATFORM_STATUS_CHANGED = "platform.status.changed"

# Agents → Core / Frontend
ALERT_CREATED = "alert.created.{severity}"          # severity: info|warning|critical
ALERT_UPDATED = "alert.updated.{alert_id}"

# Core API → Agent Runtime
AGENT_COMMAND = "agent.command.{agent_id}"          # enable|disable|set_level|set_config

# Agent Runtime → Core
AGENT_HEALTH = "agent.health.{agent_id}"


def platform_report_channel(platform_id: str) -> str:
    return f"platform.report.{platform_id}"


def alert_created_channel(severity: str) -> str:
    return f"alert.created.{severity}"


def alert_updated_channel(alert_id: str) -> str:
    return f"alert.updated.{alert_id}"


def agent_command_channel(agent_id: str) -> str:
    return f"agent.command.{agent_id}"


def agent_health_channel(agent_id: str) -> str:
    return f"agent.health.{agent_id}"
