"""Simulator 진입점."""

import asyncio
import logging
import os

from config import settings
from moth_publisher import MothPublisher
from redis_publisher import RedisPublisher
from scenario_runner import ScenarioRunner

logging.basicConfig(
    level=settings.log_level.upper(),
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
)
logger = logging.getLogger(__name__)


async def main() -> None:
    scenario_path = os.path.join(
        os.path.dirname(__file__),
        "scenarios",
        f"{settings.scenario}.yaml",
    )
    if not os.path.exists(scenario_path):
        raise FileNotFoundError(f"Scenario not found: {scenario_path}")

    moth_publisher = MothPublisher()
    redis_publisher = RedisPublisher()
    runner = ScenarioRunner(scenario_path, [moth_publisher, redis_publisher])

    logger.info("Starting simulator: scenario=%s time_scale=%.1fx", settings.scenario, settings.time_scale)

    await asyncio.gather(
        moth_publisher.run(),
        redis_publisher.run(),
        runner.run(),
    )


if __name__ == "__main__":
    asyncio.run(main())
