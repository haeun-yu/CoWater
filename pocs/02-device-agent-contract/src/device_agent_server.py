from __future__ import annotations

# 02 에이전트 서버를 바로 실행하기 위한 루트 진입점이다.

try:
    from .app import app, main
except ImportError:  # pragma: no cover - 직접 스크립트로 실행할 때의 예외 처리
    from src.app import app, main


__all__ = ["app", "main"]


if __name__ == "__main__":
    main()
