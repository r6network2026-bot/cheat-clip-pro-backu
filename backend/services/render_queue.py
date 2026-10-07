import asyncio
import json
import logging
import os
from typing import Any, Dict, Optional

from backend.schemas.render import RenderBatchRequest
from backend.services import render_service

logger = logging.getLogger("cheat-clip-pro.render-queue")

_render_queue: Optional["RedisRenderQueue"] = None


class RedisRenderQueue:
    def __init__(self, redis_client: Any, prefix: str):
        self.redis = redis_client
        self.prefix = prefix.rstrip(":")
        self.queue_key = f"{self.prefix}:render:queue"
        self.processing_key = f"{self.prefix}:render:processing"
        self.dead_letter_key = f"{self.prefix}:render:dead"
        self._stop = asyncio.Event()
        self._worker_task: Optional[asyncio.Task[None]] = None
        self._persistence_task: Optional[asyncio.Task[None]] = None

    @classmethod
    async def from_environment(cls) -> Optional["RedisRenderQueue"]:
        redis_url = os.environ.get("REDIS_URL", "").strip()
        if not redis_url:
            return None

        from redis.asyncio import Redis

        redis_client = Redis.from_url(redis_url, decode_responses=True)
        try:
            await redis_client.ping()
        except Exception:
            await redis_client.aclose()
            raise

        queue = cls(redis_client, os.environ.get("REDIS_PREFIX", "cheat-clip-pro"))
        await queue.restore()
        queue.start()
        logger.info("Persistent render queue connected to Redis.")
        return queue

    def start(self) -> None:
        self._stop.clear()
        self._worker_task = asyncio.create_task(self._run_worker())
        self._persistence_task = asyncio.create_task(self._persist_progress())

    async def close(self) -> None:
        self._stop.set()
        if self._worker_task:
            await self._worker_task
            self._worker_task = None
        if self._persistence_task:
            self._persistence_task.cancel()
            try:
                await self._persistence_task
            except asyncio.CancelledError:
                pass
            self._persistence_task = None
        await self.persist_all()
        await self.redis.aclose()

    async def restore(self) -> None:
        async for key in self.redis.scan_iter(match=f"{self.prefix}:render:batch:*"):
            payload = await self.redis.get(key)
            if payload:
                batch = json.loads(payload)
                batch_id = batch.get("batch_id")
                if batch_id:
                    render_service.RENDER_BATCHES[batch_id] = batch

        async for key in self.redis.scan_iter(match=f"{self.prefix}:render:request:*"):
            payload = await self.redis.get(key)
            if payload:
                request = RenderBatchRequest.model_validate_json(payload)
                batch_id = key.rsplit(":", 1)[-1]
                render_service.BATCH_REQUESTS[batch_id] = request

        abandoned_jobs = await self.redis.lrange(self.processing_key, 0, -1)
        if abandoned_jobs:
            async with self.redis.pipeline(transaction=True) as pipeline:
                for job in abandoned_jobs:
                    pipeline.lpush(self.queue_key, job)
                pipeline.delete(self.processing_key)
                await pipeline.execute()

    async def enqueue(
        self,
        batch_id: str,
        batch: Dict[str, Any],
        request: RenderBatchRequest,
        job_type: str,
        clip_indices: Optional[list[int]] = None,
    ) -> None:
        job = json.dumps({
            "batch_id": batch_id,
            "job_type": job_type,
            "clip_indices": clip_indices or [],
        })
        async with self.redis.pipeline(transaction=True) as pipeline:
            pipeline.set(self._batch_key(batch_id), json.dumps(batch))
            pipeline.set(self._request_key(batch_id), request.model_dump_json())
            pipeline.lpush(self.queue_key, job)
            await pipeline.execute()

    async def persist_all(self, active_only: bool = False) -> None:
        async with self.redis.pipeline(transaction=True) as pipeline:
            for batch_id, batch in render_service.RENDER_BATCHES.items():
                if active_only and not any(
                    clip.get("status") in {"downloading", "transcribing", "tracking", "rendering"}
                    for clip in batch.get("clips", [])
                ):
                    continue
                pipeline.set(self._batch_key(batch_id), json.dumps(batch))
                request = render_service.BATCH_REQUESTS.get(batch_id)
                if request:
                    pipeline.set(self._request_key(batch_id), request.model_dump_json())
            await pipeline.execute()

    async def _persist_batch(self, batch_id: str) -> None:
        batch = render_service.RENDER_BATCHES.get(batch_id)
        if batch is None:
            return
        async with self.redis.pipeline(transaction=True) as pipeline:
            pipeline.set(self._batch_key(batch_id), json.dumps(batch))
            request = render_service.BATCH_REQUESTS.get(batch_id)
            if request:
                pipeline.set(self._request_key(batch_id), request.model_dump_json())
            await pipeline.execute()

    async def _persist_progress(self) -> None:
        while not self._stop.is_set():
            try:
                await self.persist_all(active_only=True)
            except Exception:
                logger.exception("Could not persist render progress to Redis.")
            try:
                await asyncio.wait_for(self._stop.wait(), timeout=1)
            except asyncio.TimeoutError:
                pass

    async def _run_worker(self) -> None:
        while not self._stop.is_set():
            try:
                job = await self.redis.brpoplpush(
                    self.queue_key,
                    self.processing_key,
                    timeout=1,
                )
            except Exception:
                logger.exception("Render queue connection failed; retrying.")
                await asyncio.sleep(1)
                continue
            if not job:
                continue

            try:
                await self._process_job(job)
            except Exception:
                logger.exception("Could not finish a persistent render queue job.")
                try:
                    async with self.redis.pipeline(transaction=True) as pipeline:
                        pipeline.lrem(self.processing_key, 1, job)
                        pipeline.lpush(self.queue_key, job)
                        await pipeline.execute()
                except Exception:
                    logger.exception("Could not return an unprocessed job to the Redis queue.")
                await asyncio.sleep(1)

    async def _process_job(self, payload: str) -> None:
        try:
            job = json.loads(payload)
            if not isinstance(job, dict) or not isinstance(job.get("batch_id"), str):
                raise ValueError("Invalid render job payload")
            if job.get("job_type") not in {"render", "retry"}:
                raise ValueError("Unknown render job type")
        except (json.JSONDecodeError, ValueError) as exc:
            logger.error("Discarding invalid persistent render job: %s", exc)
            async with self.redis.pipeline(transaction=True) as pipeline:
                pipeline.lrem(self.processing_key, 1, payload)
                pipeline.lpush(self.dead_letter_key, payload)
                await pipeline.execute()
            return

        batch_id = job["batch_id"]
        batch = render_service.RENDER_BATCHES.get(batch_id)
        request = render_service.BATCH_REQUESTS.get(batch_id)
        if batch is None or request is None:
            logger.error("Discarding render job with missing state for batch %s.", batch_id)
            if batch is not None:
                batch["overall_status"] = "error"
                batch["error_message"] = "Persisted render request is missing."
                batch["task_scheduled"] = False
                await self._persist_batch(batch_id)
            async with self.redis.pipeline(transaction=True) as pipeline:
                pipeline.lrem(self.processing_key, 1, payload)
                pipeline.lpush(self.dead_letter_key, payload)
                await pipeline.execute()
            return

        if job["job_type"] == "retry":
            operation = render_service.process_batch_retry
            args = (batch_id, job.get("clip_indices", []))
        else:
            operation = render_service.process_batch_rendering
            args = (batch_id, request)

        try:
            await render_service.run_batch_exclusively(batch_id, operation, *args)
        except Exception as exc:
            if batch is not None:
                batch["overall_status"] = "error"
                batch["error_message"] = str(exc)
                batch["task_scheduled"] = False
            logger.exception("Persistent render job %s failed.", batch_id)
        await self._persist_batch(batch_id)
        await self.redis.lrem(self.processing_key, 1, payload)

    def _batch_key(self, batch_id: str) -> str:
        return f"{self.prefix}:render:batch:{batch_id}"

    def _request_key(self, batch_id: str) -> str:
        return f"{self.prefix}:render:request:{batch_id}"


async def initialize_render_queue() -> Optional[RedisRenderQueue]:
    global _render_queue
    _render_queue = await RedisRenderQueue.from_environment()
    return _render_queue


async def shutdown_render_queue() -> None:
    global _render_queue
    queue = _render_queue
    _render_queue = None
    if queue:
        await queue.close()


def get_render_queue() -> Optional[RedisRenderQueue]:
    return _render_queue
