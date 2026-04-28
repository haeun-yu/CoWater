from pathlib import Path
import sys

sys.path.append(str(Path(__file__).resolve().parent))

from controller.api import run


if __name__ == "__main__":
    run(Path(__file__).resolve().parent / "config.json")
