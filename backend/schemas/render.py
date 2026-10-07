from pathlib import Path
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field, field_validator

from backend.config import UPLOADS_DIR


def _validate_uploaded_asset(value: Optional[str]) -> Optional[str]:
    """Accept only existing files previously written to the managed uploads directory."""
    if not value:
        return None
    try:
        asset = Path(value).resolve(strict=True)
        uploads = UPLOADS_DIR.resolve()
    except (OSError, ValueError):
        raise ValueError("Selected media asset does not exist")
    if uploads not in asset.parents or not asset.is_file():
        raise ValueError("Selected media asset must be an uploaded file")
    return str(asset)

class RenderSettingsModel(BaseModel):
    aspect_ratio: Literal["9:16", "1:1", "4:3", "16:9", "16:9_landscape"] = "9:16"
    background_style: Literal["black", "blurred"] = "black"
    enable_face_tracking: bool = True
    streamer_preset: Literal["none", "split_top_cam", "pip_corner"] = "none"
    facecam_position: Optional[Literal["auto", "bottom_right", "top_right", "bottom_left", "top_left", "center", "left", "right"]] = "auto"
    title_text: Optional[str] = None
    title_prefix: Optional[str] = ""
    title_suffix: Optional[str] = ""
    file_name_prefix: Optional[str] = ""
    file_name_suffix: Optional[str] = ""
    title_position: Literal["auto", "safe_zone", "middle", "none"] = "auto"
    title_duration: Optional[Literal["entire", "5s", "10s"]] = "entire"
    subtitles_enabled: Optional[bool] = True
    caption_style: Literal["viral_pop", "beast_punch", "cyber_violet", "fire_red", "electric_cyan", "golden_aura", "clean_minimal", "none"] = "viral_pop"
    caption_font: str = "Outfit"
    title_font: Optional[str] = "Outfit"
    font_size: Literal["small", "medium", "big", "custom"] = "medium"
    title_font_size: Optional[Literal["small", "medium", "big", "custom"]] = "medium"
    font_size_px: Optional[int] = Field(None, ge=1, le=1000)
    title_font_size_px: Optional[int] = Field(None, ge=1, le=1000)
    text_case: Literal["uppercase", "capitalize", "lowercase"] = "uppercase"
    title_text_case: Optional[Literal["uppercase", "capitalize", "lowercase"]] = "uppercase"
    title_y_percent: Optional[float] = Field(None, ge=0, le=100)
    subtitle_y_percent: Optional[float] = Field(None, ge=0, le=100)
    subtitle_position_mode: Optional[Literal["bottom", "center"]] = "bottom"
    subtitle_center_y_percent: Optional[float] = Field(50.0, ge=0, le=100)
    # Background Music
    bgm_enabled: Optional[bool] = False
    bgm_file_path: Optional[str] = None
    bgm_volume: Optional[float] = Field(25.0, ge=0, le=100)
    bgm_start_offset: Optional[float] = Field(0.0, ge=0)
    # Hook SFX
    hook_sfx_enabled: Optional[bool] = False
    hook_sfx_file_path: Optional[str] = None
    hook_sfx_volume: Optional[float] = Field(100.0, ge=0, le=150)
    # Raw Audio / Voice Boost
    original_audio_volume: Optional[float] = Field(100.0, ge=0, le=200)
    # Watermark
    watermark_enabled: Optional[bool] = False
    watermark_type: Optional[Literal["image", "text"]] = "image"
    watermark_file_path: Optional[str] = None
    watermark_text: Optional[str] = None
    watermark_size: Optional[float] = Field(20.0, ge=5, le=50)
    watermark_opacity: Optional[float] = Field(80.0, ge=0, le=100)
    watermark_x: Optional[float] = Field(90.0, ge=0, le=100)
    watermark_y: Optional[float] = Field(8.0, ge=0, le=100)
    hardware_accel: Optional[Literal["auto", "nvenc", "amf", "qsv", "cpu"]] = "auto"
    # Multi-Segment Merged Highlight Video
    render_mode: Optional[Literal["separate", "merged"]] = "separate"
    compilation_title: Optional[str] = None

    @field_validator("bgm_file_path", "hook_sfx_file_path", "watermark_file_path")
    @classmethod
    def validate_uploaded_asset(cls, value: Optional[str]) -> Optional[str]:
        return _validate_uploaded_asset(value)

class RenderBatchRequest(BaseModel):
    video_url: str
    video_id: str
    clips: List[Dict[str, Any]]
    settings: RenderSettingsModel
    transcript: Optional[List[Dict[str, Any]]] = None

class RetryBatchRequest(BaseModel):
    clip_indices: Optional[List[int]] = None
