from pathlib import Path
import sys

sys.path.append(str(Path(__file__).resolve().parent))

from application.bootstrap import build_agent_runtime
from controller.api import run


if __name__ == "__main__":
    runtime = build_agent_runtime(Path(__file__).resolve().parent / "config.json")
    run(runtime.config_path, runtime)
