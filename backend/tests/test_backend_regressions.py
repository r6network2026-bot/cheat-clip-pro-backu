import asyncio
import json
import tempfile
import unittest
from io import BytesIO
from pathlib import Path
from unittest.mock import AsyncMock, patch

from fastapi import BackgroundTasks, HTTPException, UploadFile

from backend.routers import analyze, media, render, system
from backend.schemas import render as render_schemas
from backend.schemas.render import RenderBatchRequest, RenderSettingsModel, RetryBatchRequest
from backend.services import ai_service, render_service
from backend.services import health_service
from backend.services.render_queue import RedisRenderQueue
from backend import video_engine


class UpdateCheckTests(unittest.TestCase):
    def setUp(self):
        self.version = {
            "current_commit": "local123",
            "current_commit_full": "local123456",
            "branch": "master",
        }

    def test_reports_local_commits_that_are_not_published(self):
        with (
            patch.object(system, "get_current_git_info", return_value=self.version),
            patch.object(
                system,
                "run_git_command",
                side_effect=[
                    (0, "", ""),
                    (0, "1\t0", ""),
                    (0, "remote12", ""),
                ],
            ),
        ):
            result = system.api_check_update()

        self.assertFalse(result["update_available"])
        self.assertEqual(result["local_ahead_count"], 1)
        self.assertEqual(result["behind_count"], 0)
        self.assertEqual(result["remote_commit"], "remote12")

    def test_detects_diverged_history_without_offering_unsafe_update(self):
        with (
            patch.object(system, "get_current_git_info", return_value=self.version),
            patch.object(
                system,
                "run_git_command",
                side_effect=[
                    (0, "", ""),
                    (0, "2\t3", ""),
                    (0, "new|Remote update|2026-10-07", ""),
                    (0, "remote12", ""),
                ],
            ),
        ):
            result = system.api_check_update()

        self.assertFalse(result["update_available"])
        self.assertEqual(result["local_ahead_count"], 2)
        self.assertEqual(result["behind_count"], 3)
        self.assertEqual(len(result["changelog"]), 1)

    def test_does_not_report_latest_when_git_comparison_fails(self):
        with (
            patch.object(system, "get_current_git_info", return_value=self.version),
            patch.object(
                system,
                "run_git_command",
                side_effect=[
                    (0, "", ""),
                    (1, "", "comparison failed"),
                ],
            ),
        ):
            result = system.api_check_update()

        self.assertFalse(result["update_available"])
        self.assertIn("comparison failed", result["error"])


class RenderSettingsValidationTests(unittest.TestCase):
    def test_accepts_supported_values_and_defaults(self):
        settings = RenderSettingsModel(
            aspect_ratio="16:9",
            bgm_volume=100,
            title_y_percent=0,
        )

        self.assertEqual(settings.aspect_ratio, "16:9")
        self.assertEqual(settings.caption_style, "viral_pop")
        self.assertEqual(settings.bgm_volume, 100)
        self.assertEqual(settings.title_y_percent, 0)

    def test_rejects_out_of_range_and_unknown_settings(self):
        for field, value in (
            ("bgm_volume", 101),
            ("hook_sfx_volume", -1),
            ("font_size_px", 0),
            ("watermark_x", 101),
        ):
            with self.subTest(field=field):
                with self.assertRaises(ValueError):
                    RenderSettingsModel(**{field: value})

        with self.assertRaises(ValueError):
            RenderSettingsModel(aspect_ratio="2:1")

    def test_uploaded_asset_must_resolve_inside_uploads_directory(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            uploads_dir = Path(temp_dir) / "uploads"
            uploads_dir.mkdir()
            uploaded_file = uploads_dir / "music.mp3"
            uploaded_file.write_bytes(b"audio")
            outside_file = Path(temp_dir) / "outside.mp3"
            outside_file.write_bytes(b"audio")

            with patch.object(render_schemas, "UPLOADS_DIR", uploads_dir):
                settings = RenderSettingsModel(bgm_file_path=str(uploaded_file))
                self.assertEqual(settings.bgm_file_path, str(uploaded_file.resolve()))

                with self.assertRaises(ValueError):
                    RenderSettingsModel(bgm_file_path=str(outside_file))


class UploadPathSafetyTests(unittest.IsolatedAsyncioTestCase):
    async def test_video_upload_sanitizes_traversal_filename(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            uploads_dir = Path(temp_dir) / "uploads"
            uploads_dir.mkdir()
            upload = UploadFile(
                filename="../../outside.mp4",
                file=BytesIO(b"video"),
            )

            with (
                patch.object(media, "UPLOADS_DIR", uploads_dir),
                patch.object(
                    media,
                    "get_video_file_metadata",
                    return_value={"duration": 1, "width": 16, "height": 16},
                ),
            ):
                result = await media.upload_video(upload)

            saved_path = Path(result["file_path"]).resolve()
            self.assertIn(uploads_dir.resolve(), saved_path.parents)
            self.assertTrue(saved_path.is_file())
            self.assertEqual(saved_path.name, result["saved_name"])

    def test_media_path_guard_rejects_paths_outside_managed_roots(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            outside_path = Path(temp_dir) / "outside.mp4"
            self.assertFalse(media._is_safe_path(outside_path))


class RenderQueueTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        render_service.RENDER_BATCHES.clear()
        render_service.BATCH_REQUESTS.clear()
        render_service._BATCH_LOCKS.clear()

    def tearDown(self):
        render_service.RENDER_BATCHES.clear()
        render_service.BATCH_REQUESTS.clear()
        render_service._BATCH_LOCKS.clear()

    def make_request(self):
        return RenderBatchRequest(
            video_url="https://www.youtube.com/watch?v=video123",
            video_id="video123",
            clips=[{"start_time": 1, "end_time": 5, "title": "Test"}],
            settings=RenderSettingsModel(),
        )

    async def test_start_batch_registers_status_request_and_worker(self):
        request = self.make_request()
        background_tasks = BackgroundTasks()
        worker = AsyncMock()

        with patch.object(render, "process_batch_rendering", worker):
            response = await render.start_batch_render(request, background_tasks)
            batch_id = response["batch_id"]
            self.assertTrue(render_service.RENDER_BATCHES[batch_id]["task_scheduled"])
            await background_tasks()

        self.assertEqual(response["total_clips"], 1)
        self.assertEqual(render_service.RENDER_BATCHES[batch_id]["overall_status"], "running")
        self.assertFalse(render_service.RENDER_BATCHES[batch_id]["task_scheduled"])
        self.assertIs(render_service.BATCH_REQUESTS[batch_id], request)
        worker.assert_awaited_once_with(batch_id, request)

    async def test_start_batch_persists_to_redis_instead_of_background_tasks(self):
        request = self.make_request()
        background_tasks = BackgroundTasks()
        queue = AsyncMock()

        with patch.object(render, "get_render_queue", return_value=queue):
            response = await render.start_batch_render(request, background_tasks)

        batch_id = response["batch_id"]
        queue.enqueue.assert_awaited_once_with(
            batch_id,
            render_service.RENDER_BATCHES[batch_id],
            request,
            "render",
        )
        self.assertEqual(background_tasks.tasks, [])

    async def test_retry_rejects_a_batch_that_is_already_scheduled(self):
        batch_id = "batch_retry_lock"
        render_service.RENDER_BATCHES[batch_id] = {
            "batch_id": batch_id,
            "overall_status": "running",
            "task_scheduled": True,
            "clips": [{"status": "error", "progress_percent": 0}],
        }
        render_service.BATCH_REQUESTS[batch_id] = self.make_request()

        with self.assertRaises(HTTPException) as raised:
            await render.retry_batch_rendering(batch_id, BackgroundTasks(), RetryBatchRequest())

        self.assertEqual(raised.exception.status_code, 409)

    async def test_retry_schedules_only_failed_clip_indices(self):
        batch_id = "batch_retry_failed"
        render_service.RENDER_BATCHES[batch_id] = {
            "batch_id": batch_id,
            "overall_status": "error",
            "task_scheduled": False,
            "clips": [
                {"status": "error", "progress_percent": 100},
                {"status": "completed", "progress_percent": 100},
            ],
        }
        render_service.BATCH_REQUESTS[batch_id] = self.make_request()
        background_tasks = BackgroundTasks()
        worker = AsyncMock()

        with patch.object(render, "process_batch_retry", worker):
            response = await render.retry_batch_rendering(
                batch_id,
                background_tasks,
                RetryBatchRequest(),
            )
            self.assertTrue(render_service.RENDER_BATCHES[batch_id]["task_scheduled"])
            self.assertEqual(render_service.RENDER_BATCHES[batch_id]["clips"][0]["status"], "pending")
            await background_tasks()

        self.assertEqual(response["retrying_clips"], [0])
        worker.assert_awaited_once_with(batch_id, [0])
        self.assertFalse(render_service.RENDER_BATCHES[batch_id]["task_scheduled"])

    async def test_retry_persists_to_redis_instead_of_background_tasks(self):
        batch_id = "batch_retry_redis"
        batch = {
            "batch_id": batch_id,
            "overall_status": "error",
            "task_scheduled": False,
            "clips": [
                {"status": "error", "progress_percent": 100, "error": "failed"},
                {"status": "completed", "progress_percent": 100},
            ],
        }
        request = self.make_request()
        render_service.RENDER_BATCHES[batch_id] = batch
        render_service.BATCH_REQUESTS[batch_id] = request
        background_tasks = BackgroundTasks()
        queue = AsyncMock()

        with patch.object(render, "get_render_queue", return_value=queue):
            response = await render.retry_batch_rendering(
                batch_id,
                background_tasks,
                RetryBatchRequest(),
            )

        queue.enqueue.assert_awaited_once_with(batch_id, batch, request, "retry", [0])
        self.assertEqual(response["retrying_clips"], [0])
        self.assertTrue(batch["task_scheduled"])
        self.assertEqual(batch["clips"][0]["status"], "pending")
        self.assertEqual(background_tasks.tasks, [])

    async def test_failed_redis_enqueue_rolls_back_retry_state(self):
        batch_id = "batch_retry_redis_failure"
        original_batch = {
            "batch_id": batch_id,
            "overall_status": "error",
            "task_scheduled": False,
            "clips": [{"status": "error", "progress_percent": 100, "error": "failed"}],
        }
        render_service.RENDER_BATCHES[batch_id] = original_batch
        render_service.BATCH_REQUESTS[batch_id] = self.make_request()
        queue = AsyncMock()
        queue.enqueue.side_effect = ConnectionError("Redis unavailable")

        with patch.object(render, "get_render_queue", return_value=queue):
            with self.assertRaises(HTTPException) as raised:
                await render.retry_batch_rendering(
                    batch_id,
                    BackgroundTasks(),
                    RetryBatchRequest(),
                )

        self.assertEqual(raised.exception.status_code, 503)
        self.assertEqual(original_batch["overall_status"], "error")
        self.assertFalse(original_batch["task_scheduled"])
        self.assertEqual(original_batch["clips"][0]["status"], "error")

    async def test_batch_worker_lock_serializes_operations_for_same_batch(self):
        active = 0
        max_active = 0
        order = []

        async def operation(name):
            nonlocal active, max_active
            active += 1
            max_active = max(max_active, active)
            order.append(f"start-{name}")
            await asyncio.sleep(0)
            order.append(f"end-{name}")
            active -= 1

        batch_id = "batch_exclusive"
        render_service.RENDER_BATCHES[batch_id] = {
            "overall_status": "running",
            "task_scheduled": True,
        }

        await asyncio.gather(
            render_service.run_batch_exclusively(batch_id, operation, "first"),
            render_service.run_batch_exclusively(batch_id, operation, "second"),
        )

        self.assertEqual(max_active, 1)
        self.assertEqual(order[0], "start-first")
        self.assertEqual(order[1], "end-first")
        self.assertEqual(order[2], "start-second")
        self.assertFalse(render_service.RENDER_BATCHES[batch_id]["task_scheduled"])


class FakeRedisPipeline:
    def __init__(self, redis_client):
        self.redis = redis_client
        self.commands = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, traceback):
        return False

    def set(self, key, value):
        self.commands.append(("set", key, value))

    def lpush(self, key, value):
        self.commands.append(("lpush", key, value))

    def lrem(self, key, count, value):
        self.commands.append(("lrem", key, count, value))

    def delete(self, key):
        self.commands.append(("delete", key))

    async def execute(self):
        for item in self.commands:
            command, key, *args = item
            if command == "set":
                self.redis.values[key] = args[0]
            elif command == "lpush":
                self.redis.lists.setdefault(key, []).insert(0, args[0])
            elif command == "lrem":
                await self.redis.lrem(key, args[0], args[1])
            elif command == "delete":
                await self.redis.delete(key)


class FakeRedis:
    def __init__(self):
        self.values = {}
        self.lists = {}

    def pipeline(self, transaction=True):
        return FakeRedisPipeline(self)

    async def scan_iter(self, match):
        prefix = match.removesuffix("*")
        for key in list(self.values):
            if key.startswith(prefix):
                yield key

    async def get(self, key):
        return self.values.get(key)

    async def ping(self):
        return True

    async def lpush(self, key, value):
        self.lists.setdefault(key, []).insert(0, value)

    async def lrange(self, key, start, end):
        values = self.lists.get(key, [])
        return values[start:] if end == -1 else values[start:end + 1]

    async def lrem(self, key, count, value):
        values = self.lists.get(key, [])
        removed = 0
        while value in values and (count == 0 or removed < count):
            values.remove(value)
            removed += 1
        return removed

    async def delete(self, key):
        self.lists.pop(key, None)

    async def aclose(self):
        return None


class PersistentRenderQueueTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        render_service.RENDER_BATCHES.clear()
        render_service.BATCH_REQUESTS.clear()

    def tearDown(self):
        render_service.RENDER_BATCHES.clear()
        render_service.BATCH_REQUESTS.clear()

    def make_request(self):
        return RenderBatchRequest(
            video_url="https://www.youtube.com/watch?v=persisted",
            video_id="persisted",
            clips=[{"start_time": 2, "end_time": 7}],
            settings=RenderSettingsModel(),
        )

    async def test_enqueue_persists_batch_request_and_job_for_restart(self):
        redis_client = FakeRedis()
        queue = RedisRenderQueue(redis_client, "test")
        batch_id = "batch_persist"
        batch = {
            "batch_id": batch_id,
            "overall_status": "running",
            "task_scheduled": True,
            "clips": [{"status": "pending", "progress_percent": 0}],
        }
        request = self.make_request()

        await queue.enqueue(batch_id, batch, request, "render")
        render_service.RENDER_BATCHES.clear()
        render_service.BATCH_REQUESTS.clear()

        restored_queue = RedisRenderQueue(redis_client, "test")
        await restored_queue.restore()

        self.assertEqual(render_service.RENDER_BATCHES[batch_id], batch)
        self.assertEqual(render_service.BATCH_REQUESTS[batch_id], request)
        self.assertEqual(await redis_client.lrange(queue.queue_key, 0, -1), [
            '{"batch_id": "batch_persist", "job_type": "render", "clip_indices": []}'
        ])

    async def test_configured_redis_is_required_and_starts_persistent_mode(self):
        from redis.asyncio import Redis

        redis_client = FakeRedis()
        with (
            patch.dict("os.environ", {"REDIS_URL": "redis://redis.test/0", "REDIS_PREFIX": "test"}),
            patch.object(Redis, "from_url", return_value=redis_client),
            patch.object(RedisRenderQueue, "start") as start_worker,
        ):
            queue = await RedisRenderQueue.from_environment()

        self.assertIsNotNone(queue)
        self.assertEqual(queue.prefix, "test")
        start_worker.assert_called_once_with()

    async def test_configured_redis_connection_failure_is_not_silently_ignored(self):
        from redis.asyncio import Redis

        redis_client = FakeRedis()
        redis_client.ping = AsyncMock(side_effect=ConnectionError("Redis unavailable"))
        redis_client.aclose = AsyncMock()
        with (
            patch.dict("os.environ", {"REDIS_URL": "redis://redis.test/0"}),
            patch.object(Redis, "from_url", return_value=redis_client),
        ):
            with self.assertRaisesRegex(ConnectionError, "Redis unavailable"):
                await RedisRenderQueue.from_environment()

        redis_client.aclose.assert_awaited_once()

    async def test_restore_requeues_job_left_in_processing_list(self):
        redis_client = FakeRedis()
        queue = RedisRenderQueue(redis_client, "test")
        abandoned_job = '{"batch_id": "batch_crashed", "job_type": "render", "clip_indices": []}'
        redis_client.lists[queue.processing_key] = [abandoned_job]

        await queue.restore()

        self.assertEqual(await redis_client.lrange(queue.queue_key, 0, -1), [abandoned_job])
        self.assertEqual(await redis_client.lrange(queue.processing_key, 0, -1), [])

    async def test_worker_persists_completion_before_acknowledging_job(self):
        redis_client = FakeRedis()
        queue = RedisRenderQueue(redis_client, "test")
        batch_id = "batch_ack"
        payload = json.dumps({
            "batch_id": batch_id,
            "job_type": "render",
            "clip_indices": [],
        })
        batch = {
            "batch_id": batch_id,
            "overall_status": "completed",
            "task_scheduled": False,
            "clips": [],
        }
        render_service.RENDER_BATCHES[batch_id] = batch
        render_service.BATCH_REQUESTS[batch_id] = self.make_request()
        redis_client.lists[queue.processing_key] = [payload]

        with patch.object(render_service, "run_batch_exclusively", AsyncMock()) as worker:
            await queue._process_job(payload)

        worker.assert_awaited_once()
        persisted = json.loads(await redis_client.get(queue._batch_key(batch_id)))
        self.assertEqual(persisted["overall_status"], "completed")
        self.assertEqual(await redis_client.lrange(queue.processing_key, 0, -1), [])

    async def test_invalid_job_is_dead_lettered_instead_of_retried_forever(self):
        redis_client = FakeRedis()
        queue = RedisRenderQueue(redis_client, "test")
        payload = '{"job_type": "unknown"}'
        redis_client.lists[queue.processing_key] = [payload]

        await queue._process_job(payload)

        self.assertEqual(await redis_client.lrange(queue.processing_key, 0, -1), [])
        self.assertEqual(await redis_client.lrange(queue.dead_letter_key, 0, -1), [payload])

    async def test_redis_is_optional_when_environment_has_no_url(self):
        from backend.services import render_queue as render_queue_module

        with patch.dict("os.environ", {"REDIS_URL": ""}):
            queue = await RedisRenderQueue.from_environment()

        self.assertIsNone(queue)
        self.assertIsNone(render_queue_module.get_render_queue())


class TempCleanupTests(unittest.IsolatedAsyncioTestCase):
    async def test_clear_temp_is_rejected_while_a_render_is_running(self):
        render_service.RENDER_BATCHES.clear()
        render_service.RENDER_BATCHES["batch_running"] = {
            "overall_status": "running",
            "task_scheduled": False,
        }
        clear_files = AsyncMock()
        try:
            with patch.object(system, "clear_temp_files", clear_files):
                with self.assertRaises(HTTPException) as raised:
                    await system.clear_temp_folder(authorized=True)

            self.assertEqual(raised.exception.status_code, 409)
            clear_files.assert_not_awaited()
        finally:
            render_service.RENDER_BATCHES.clear()


class HealthEndpointTests(unittest.TestCase):
    def test_health_reports_all_required_render_dependencies(self):
        directory_health = {"ok": True, "writable": True, "free_bytes": 1000}
        with (
            patch.object(health_service.shutil, "which", return_value="ffmpeg"),
            patch.object(health_service, "ACTIVE_ENCODER_NAME", "h264_qsv"),
            patch.object(health_service, "has_subtitles_filter", return_value=True),
            patch.object(
                health_service,
                "detect_hardware_support",
                return_value={"qsv": True, "cpu": True},
            ),
            patch.object(health_service, "_check_directory", return_value=directory_health),
        ):
            status = health_service.get_render_health()

        self.assertEqual(status["status"], "healthy")
        self.assertEqual(
            set(status["checks"]),
            {"ffmpeg", "libass", "encoder", "temp_storage", "uploads"},
        )

    def test_health_reports_degraded_when_required_dependency_is_unavailable(self):
        with (
            patch.object(health_service.shutil, "which", return_value=None),
            patch.object(health_service, "detect_hardware_support", return_value={"cpu": True}),
            patch.object(health_service, "_check_directory", return_value={"ok": False}),
        ):
            status = health_service.get_render_health()

        self.assertEqual(status["status"], "unhealthy")
        self.assertFalse(status["checks"]["ffmpeg"]["ok"])
        self.assertFalse(status["checks"]["libass"]["ok"])
        self.assertFalse(status["checks"]["encoder"]["ok"])

    def test_health_route_is_mounted_and_returns_json(self):
        from fastapi.testclient import TestClient

        from backend.main import app

        with (
            patch.dict("os.environ", {"REDIS_URL": ""}),
            patch.object(
                analyze,
                "get_render_health",
                return_value={"status": "healthy", "checks": {"ffmpeg": {"ok": True}}},
            ),
            TestClient(app) as client,
        ):
            response = client.get("/api/health")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "ok")
        self.assertEqual(response.json()["render_health"]["status"], "healthy")


class GeminiMockTests(unittest.TestCase):
    def test_mock_key_returns_fallback_models_without_creating_client(self):
        with patch.object(ai_service.genai, "Client") as client:
            models = ai_service.list_available_gemini_models("mock")

        self.assertEqual(models[0], "gemini-2.5-flash")
        self.assertIn("gemini-2.5-pro", models)
        client.assert_not_called()


class FFmpegSubtitlePreflightTests(unittest.TestCase):
    def test_filter_probe_detects_subtitles_filter(self):
        completed = type(
            "Completed",
            (),
            {"returncode": 0, "stdout": " ... subtitles V->V Apply subtitles to the input video.\n"},
        )()
        with patch.object(video_engine.subprocess, "run", return_value=completed):
            self.assertTrue(video_engine._ffmpeg_has_filter("ffmpeg", "subtitles"))

    def test_render_fails_before_ffmpeg_when_libass_filter_is_missing(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            input_path = Path(temp_dir) / "input.mp4"
            subtitle_path = Path(temp_dir) / "captions.ass"
            input_path.write_bytes(b"x" * 1024)
            subtitle_path.write_text("[Script Info]\n", encoding="utf-8")

            with (
                patch.object(video_engine.shutil, "which", return_value="ffmpeg"),
                patch.object(video_engine, "_ffmpeg_has_filter", return_value=False),
                patch.object(video_engine, "is_valid_mp4", return_value=True),
                patch.object(video_engine, "build_ffmpeg_filtergraph") as build_filtergraph,
            ):
                with self.assertRaisesRegex(RuntimeError, "requires an FFmpeg build with libass"):
                    video_engine.render_clip_to_mp4(
                        str(input_path),
                        str(Path(temp_dir) / "output.mp4"),
                        enable_face_tracking=False,
                        ass_subtitles_path=str(subtitle_path),
                    )

            build_filtergraph.assert_not_called()


if __name__ == "__main__":
    unittest.main()
