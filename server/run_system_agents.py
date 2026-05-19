"""
server/run_system_agents.py

모든 System Agent를 개별 프로세스로 실행하는 런처.
각 에이전트 디렉토리의 system_agent.py를 서브프로세스로 기동합니다.
"""
from __future__ import annotations

import argparse
import logging
import os
import subprocess
import sys
import time
from pathlib import Path

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="[%(name)s] %(message)s")

HERE = Path(__file__).resolve().parent

AGENTS = [
    {"dir": "request-handler",  "port": 9116, "role": "request_handler"},
    {"dir": "device-bridge",    "port": 9110, "role": "device_bridge"},
    {"dir": "mission-planner",  "port": 9111, "role": "mission_planner"},
    {"dir": "policy-manager",   "port": 9112, "role": "policy_manager"},
    {"dir": "system-sentinel",  "port": 9113, "role": "system_sentinel"},
    {"dir": "insight-reporter", "port": 9114, "role": "insight_reporter"},
]


def main() -> None:
    parser = argparse.ArgumentParser(description="Run all CoWater System Agents")
    parser.add_argument("--agents", nargs="*", help="Which agents to run (default: all)")
    args = parser.parse_args()

    selected = set(args.agents or [a["role"] for a in AGENTS])
    processes: list[subprocess.Popen] = []

    for agent in AGENTS:
        if agent["role"] not in selected:
            continue
        agent_dir = HERE / agent["dir"]
        entry = agent_dir / "system_agent.py"
        config = agent_dir / "config.json"
        if not entry.exists():
            logger.warning(f"{entry} not found, skipping {agent['role']}")
            continue
        cmd = [sys.executable, str(entry), "--config", str(config)]
        proc = subprocess.Popen(cmd, cwd=str(agent_dir))
        processes.append(proc)
        logger.info(f"{agent['role']} (port {agent['port']}) started with pid={proc.pid}")
        time.sleep(0.3)

    logger.info(f"All {len(processes)} agent(s) started. Press Ctrl+C to stop.")
    try:
        for proc in processes:
            proc.wait()
    except KeyboardInterrupt:
        logger.info("Shutting down...")
        for proc in processes:
            proc.terminate()
        for proc in processes:
            proc.wait()
        logger.info("All agents stopped.")


if __name__ == "__main__":
    main()
