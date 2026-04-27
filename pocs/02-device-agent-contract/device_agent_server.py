from __future__ import annotations

# 02 에이전트 서버를 바로 실행하기 위한 루트 진입점이다.

from src.app import app, main


__all__ = ["app", "main"]


if __name__ == "__main__":
    main()
