"""Agent 등록 및 생명주기 관리."""

from __future__ import annotations

import logging

import redis.asyncio as aioredis

from base import Agent, AgentLevel

logger = logging.getLogger(__name__)


class AgentRegistry:
    def __init__(self) -> None:
        self._agents: dict[str, Agent] = {}

    def register(self, agent: Agent) -> None:
        self._agents[agent.agent_id] = agent
        logger.info("Registered agent: %s (%s)", agent.agent_id, agent.name)

    def get(self, agent_id: str) -> Agent | None:
        return self._agents.get(agent_id)

    def all(self) -> list[Agent]:
        return list(self._agents.values())

    def enabled(self) -> list[Agent]:
        return [a for a in self._agents.values() if a.enabled]

    def enable(self, agent_id: str) -> bool:
        agent = self._agents.get(agent_id)
        if agent is None:
            return False
        agent.enabled = True
        logger.info("Agent enabled: %s", agent_id)
        return True

    def disable(self, agent_id: str) -> bool:
        agent = self._agents.get(agent_id)
        if agent is None:
            return False
        agent.enabled = False
        logger.info("Agent disabled: %s", agent_id)
        return True

    def set_level(self, agent_id: str, level: AgentLevel) -> bool:
        agent = self._agents.get(agent_id)
        if agent is None:
            return False
        agent.set_level(level)
        return True

    def set_config(self, agent_id: str, config: dict) -> bool:
        agent = self._agents.get(agent_id)
        if agent is None:
            return False
        agent.config.update(config)
        logger.info("Agent config updated: %s", agent_id)
        return True
