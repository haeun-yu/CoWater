from __future__ import annotations

import argparse
import signal
import subprocess
import sys
import time
from pathlib import Path

from system_agent import ROLE_PROFILES


def main() -> int:
    parser = argparse.ArgumentParser(description="Run all CoWater System Agent role processes.")
    parser.add_argument("--config", default=str(Path(__file__).resolve().parent / "config.json"))
    args = parser.parse_args()

    root = Path(__file__).resolve().parent
    children: list[subprocess.Popen] = []

    def stop_children(*_: object) -> None:
        for child in children:
            if child.poll() is None:
                child.terminate()

    signal.signal(signal.SIGINT, stop_children)
    signal.signal(signal.SIGTERM, stop_children)

    try:
        for role in ROLE_PROFILES:
            children.append(
                subprocess.Popen(
                    [sys.executable, str(root / "system_agent.py"), "--config", args.config, "--role", role],
                    cwd=str(root.parent.parent),
                )
            )
        while children:
            for child in list(children):
                code = child.poll()
                if code is not None:
                    children.remove(child)
                    if code != 0:
                        stop_children()
                        return code
            time.sleep(1)
    finally:
        stop_children()
        for child in children:
            child.wait(timeout=10)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
