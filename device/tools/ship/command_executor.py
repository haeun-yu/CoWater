from __future__ import annotations

import random
from agent.state import utc_now


class CommandExecutor:
    def __init__(self) -> None:
        self.history: list[dict] = []

    def execute(self, command: dict) -> dict:
        """Execute Ship (Control Command Center) command.
        
        Simulates task execution with optional failure scenarios.
        Low failure rate for ship commands (5%).
        """
        self.history.append({"at": utc_now(), "command": command})
        self.history = self.history[-20:]
        
        action = str(command.get('action') or '').lower()
        
        # Simulate low failure rate for ship commands
        if random.random() < 0.05:  # 5% failure rate
            return {
                'delivered': False,
                'command': command,
                'error': f'Ship command failed: {action}',
                'at': utc_now()
            }
        
        return {
            'delivered': True,
            'command': command,
            'at': utc_now()
        }

