from __future__ import annotations

try:
    from .app import app, main
except ImportError:  # pragma: no cover - direct script execution fallback
    from src.app import app, main


__all__ = ["app", "main"]


if __name__ == "__main__":
    main()
