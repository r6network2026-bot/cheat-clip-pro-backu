from importlib import import_module

_SERVICE_MODULES = {
    "KNOWN_FLASH_MODELS": "ai_service",
    "get_flash_models_for_key": "ai_service",
    "list_available_gemini_models": "ai_service",
    "parse_gemini_model_sort_key": "ai_service",
    "raw_clip_download_jobs": "download_service",
    "raw_download_jobs": "download_service",
    "run_raw_clip_download_job": "download_service",
    "run_raw_download_job": "download_service",
    "BATCH_REQUESTS": "render_service",
    "RENDER_BATCHES": "render_service",
    "process_batch_rendering": "render_service",
    "process_batch_retry": "render_service",
    "render_single_batch_clip": "render_service",
    "update_batch_summary_and_zip": "render_service",
    "clear_temp_files": "system_service",
    "get_current_git_info": "system_service",
    "get_dir_size_and_count": "system_service",
    "get_temp_storage_summary": "system_service",
    "run_git_command": "system_service",
    "trigger_detached_restart": "system_service",
    "check_single_supadata_key": "youtube_service",
    "fetch_transcript": "youtube_service",
    "fetch_transcript_cli": "youtube_service",
    "fetch_transcript_supadata": "youtube_service",
    "fetch_transcript_ytdlp": "youtube_service",
    "fetch_video_metadata": "youtube_service",
    "get_supadata_keys": "youtube_service",
    "get_supadata_usage_data": "youtube_service",
    "get_youtube_oembed_title": "youtube_service",
    "normalize_transcript": "youtube_service",
}

__all__ = list(_SERVICE_MODULES)


def __getattr__(name: str):
    module_name = _SERVICE_MODULES.get(name)
    if module_name is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    value = getattr(import_module(f"backend.services.{module_name}"), name)
    globals()[name] = value
    return value
