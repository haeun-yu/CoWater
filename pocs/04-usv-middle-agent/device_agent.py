from pathlib import Path
import sys

poc_dir = Path(__file__).resolve().parent
sys.path.insert(0, str(poc_dir))

from controller.api import run


if __name__ == "__main__":
    run(Path(__file__).resolve().parent / "config.json")
