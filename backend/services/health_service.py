import os
import shutil
from pathlib import Path
from typing import Any, Dict

from backend.config import ACTIVE_ENCODER_NAME, TEMP_DIR, UPLOADS_DIR
from backend.video_engine import detect_hardware_support, has_subtitles_filter


def _check_directory(path: Path) -> Dict[str, Any]:
    try:
        exists = path.is_dir()
        writable = exists and os.access(path, os.W_OK)
        usage = shutil.disk_usage(path) if exists else None
    except OSError as exc:
        return {
            "ok": False,
            "writable": False,
            "error": str(exc),
        }

    result: Dict[str, Any] = {
        "ok": bool(exists and writable and usage is not None),
        "writable": bool(writable),
    }
    if usage is not None:
        result.update({
            "free_bytes": usage.free,
            "total_bytes": usage.total,
        })
    if not exists:
        result["error"] = "Directory is unavailable"
    elif not writable:
        result["error"] = "Directory is not writable"
    return result


def get_render_health() -> Dict[str, Any]:
    """Return cached FFmpeg capability checks and current media storage health."""
    ffmpeg_available = shutil.which("ffmpeg") is not None
    subtitles_available = ffmpeg_available and has_subtitles_filter()
    hardware_support = detect_hardware_support()
    encoder_key = {
        "h264_nvenc": "nvenc",
        "h264_amf": "amf",
        "h264_qsv": "qsv",
        "libx264": "cpu",
    }.get(ACTIVE_ENCODER_NAME)
    encoder_available = bool(
        ffmpeg_available
        and encoder_key
        and hardware_support.get(encoder_key, False)
    )
    checks = {
        "ffmpeg": {"ok": ffmpeg_available},
        "libass": {"ok": subtitles_available},
        "encoder": {
            "ok": encoder_available,
            "active": ACTIVE_ENCODER_NAME,
        },
        "temp_storage": _check_directory(TEMP_DIR),
        "uploads": _check_directory(UPLOADS_DIR),
    }
    healthy = all(check["ok"] for check in checks.values())
    return {
        "status": "healthy" if healthy else "unhealthy",
        "checks": checks,
    }
