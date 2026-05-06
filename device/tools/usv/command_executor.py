from __future__ import annotations

import random
from agent.state import utc_now


class CommandExecutor:
    def __init__(self) -> None:
        self.history: list[dict] = []

    def execute(self, command: dict) -> dict:
        """Execute USV command.
        
        Simulates task execution with optional failure scenarios.
        Certain actions have probability of failure (e.g., mine_sweep at 10%).
        """
        self.history.append({"at": utc_now(), "command": command})
        self.history = self.history[-20:]
        
        action = str(command.get('action') or '').lower()
        
        # Simulate failure for certain actions (e.g., 10% chance for mine sweep)
        if action in ['deploy_mine_sweeper', 'sweep_mine', 'detonate']:
            if random.random() < 0.1:  # 10% failure rate
                return {
                    'delivered': False,
                    'command': command,
                    'error': f'USV command failed: {action}',
                    'at': utc_now()
                }
        
        return {
            'delivered': True,
            'command': command,
            'at': utc_now()
        }

