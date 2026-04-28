from pathlib import Path
import sys

# Add both POC directory and pocs directory to sys.path for shared module access
poc_dir = Path(__file__).resolve().parent
pocs_dir = poc_dir.parent
sys.path.insert(0, str(poc_dir))
sys.path.insert(0, str(pocs_dir))

from controller.api import run


if __name__ == "__main__":
    run(Path(__file__).resolve().parent / "config.json")
