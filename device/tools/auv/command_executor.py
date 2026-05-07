from __future__ import annotations

import random
from typing import Any

from agent.state import utc_now


class CommandExecutor:
    def __init__(self) -> None:
        self.history: list[dict] = []

    def execute(self, command: dict) -> dict:
        """Execute AUV command.
        
        Simulates task execution with optional failure scenarios.
        Certain actions have probability of failure (e.g., survey_depth at 10%).
        """
        self.history.append({"at": utc_now(), "command": command})
        self.history = self.history[-20:]
        action = str(command.get("action") or "")
        params = command.get("params") or {}
        location = params.get("location") or {}
        
        # Simulate random failures for risky actions
        if action.lower() in ["survey_depth", "scan_area", "mine_detection"]:
            if random.random() < 0.1:  # 10% failure rate
                return {
                    "delivered": False,
                    "command": command,
                    "error": f"AUV command failed: {action}",
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
            "confidence": 0.9,
            "artifacts": [],
        }

        if action == "survey_depth":
            result["confidence"] = 0.93
            result["artifacts"] = [
                {
                    "type": "mine_location_estimate",
                    "location": location,
                    "confidence": 0.93,
                },
                {
                    "type": "sonar_evidence",
                    "frame_id": f"auv-survey-{utc_now()}",
                },
            ]
        elif action == "scan_area":
            result["confidence"] = 0.88
            result["artifacts"] = [
                {
                    "type": "coverage_map",
                    "location": location,
                    "coverage_ratio": 1.0,
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
