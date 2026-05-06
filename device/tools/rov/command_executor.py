from __future__ import annotations

import random
from typing import Any

from agent.state import utc_now


class CommandExecutor:
    def __init__(self) -> None:
        self.history: list[dict] = []

    def execute(self, command: dict) -> dict:
        """Execute ROV command.
        
        Simulates task execution with optional failure scenarios.
        Certain actions have probability of failure (e.g., remove_mine at 15%).
        """
        self.history.append({"at": utc_now(), "command": command})
        self.history = self.history[-20:]
        action = str(command.get("action") or "")
        params = command.get("params") or {}
        location = params.get("location") or {}
        previous_step_results = params.get("previous_step_results") or []
        
        # Simulate random failures for risky actions (mine removal is riskier: 15%)
        if action.lower() in ["remove_mine", "detonate_mine"]:
            if random.random() < 0.15:  # 15% failure rate for mine removal
                return {
                    "delivered": False,
                    "command": command,
                    "error": f"ROV command failed: {action}",
                    "at": utc_now(),
                    "status": "failed"
                }
        elif action.lower() in ["inspect_target", "scan_target"]:
            if random.random() < 0.08:  # 8% failure rate for inspection
                return {
                    "delivered": False,
                    "command": command,
                    "error": f"ROV command failed: {action}",
                    "at": utc_now(),
                    "status": "failed"
                }

        result: dict[str, Any] = {
            "delivered": True,
            "command": command,
            "at": utc_now(),
            "status": "completed",
            "usable_output": True,
            "failure_reason": None,
            "confidence": 0.91,
            "artifacts": [],
        }

        if action == "remove_mine":
            result["confidence"] = 0.95
            result["artifacts"] = [
                {
                    "type": "mine_removal_confirmation",
                    "location": location,
                    "used_previous_step_results": bool(previous_step_results),
                },
                {
                    "type": "manipulator_log",
                    "action": "remove_mine",
                },
            ]
        elif action == "inspect_target":
            result["confidence"] = 0.9
            result["artifacts"] = [
                {
                    "type": "inspection_report",
                    "location": location,
                }
            ]
        else:
            result["artifacts"] = [
                {
                    "type": "command_ack",
                    "action": action,
                }
            ]

        simulate_outcome = params.get("simulate_outcome") or {}
        if params.get("simulate_failure") is True:
            simulate_outcome = {
                **simulate_outcome,
                "status": "failed",
                "usable_output": False,
                "failure_reason": simulate_outcome.get("failure_reason") or "simulated_failure",
            }
        if isinstance(simulate_outcome, dict) and simulate_outcome:
            if "status" in simulate_outcome:
                result["status"] = str(simulate_outcome["status"])
            if "usable_output" in simulate_outcome:
                result["usable_output"] = bool(simulate_outcome["usable_output"])
            if "failure_reason" in simulate_outcome:
                result["failure_reason"] = simulate_outcome["failure_reason"]
            if "confidence" in simulate_outcome:
                result["confidence"] = float(simulate_outcome["confidence"])
            if "artifacts" in simulate_outcome and isinstance(simulate_outcome["artifacts"], list):
                result["artifacts"] = list(simulate_outcome["artifacts"])
            if "delivered" in simulate_outcome:
                result["delivered"] = bool(simulate_outcome["delivered"])
            if result.get("status") == "failed" and "usable_output" not in simulate_outcome:
                result["usable_output"] = False

        return result
