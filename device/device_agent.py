from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))

from controller.api import run

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="CoWater Device Agent")
    parser.add_argument(
        "--type",
        choices=["usv", "auv", "rov", "ship"],
        required=True,
        help="디바이스 타입 (usv / auv / rov / ship)",
    )
    parser.add_argument(
        "--layer",
        choices=["lower", "middle"],
        required=True,
        help="에이전트 계층 (lower / middle)",
    )
    parser.add_argument("--config", type=Path, default=None, help="config.json 경로 (미지정 시 configs/{type}-{layer}.json)")
    parser.add_argument("--host", default=None, help="서버 host 오버라이드")
    parser.add_argument("--port", type=int, default=None, help="서버 port 오버라이드")
    args = parser.parse_args()

    default_config = Path(__file__).parent / "configs" / f"{args.type}-{args.layer}.json"
    config_path = (args.config or default_config).resolve()

    if not config_path.exists():
        print(f"config 파일을 찾을 수 없습니다: {config_path}")
        sys.exit(1)

    run(config_path, host_override=args.host, port_override=args.port)
