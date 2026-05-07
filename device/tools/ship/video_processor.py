from __future__ import annotations

from typing import Any, Optional

from agent.state import utc_now


class VideoProcessor:
    def __init__(self) -> None:
        self.is_recording: bool = False
        self.resolution: str = "4K"
        self.fps: int = 30
        self.frames_captured: int = 0
        self.last_frame_at: str | None = None

    def capture_frame(self) -> Optional[bytes]:
        if not self.is_recording:
            self.start_recording()
        self.frames_captured += 1
        self.last_frame_at = utc_now()
        return f"frame-{self.frames_captured}".encode("utf-8")

    def start_recording(self) -> bool:
        self.is_recording = True
        return True

    def stop_recording(self) -> bool:
        self.is_recording = False
        return True

    def get_status(self) -> dict[str, Any]:
        return {
            "recording": self.is_recording,
            "resolution": self.resolution,
            "fps": self.fps,
            "frames_captured": self.frames_captured,
            "last_frame_at": self.last_frame_at,
        }
