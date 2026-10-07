import os
import unittest
from uuid import uuid4

from backend.schemas.render import RenderBatchRequest, RenderSettingsModel
from backend.services import render_service
from backend.services.render_queue import RedisRenderQueue


class RedisRenderQueueIntegrationTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        redis_url = os.environ.get("REDIS_URL", "").strip()
        if not redis_url:
            self.skipTest("Set REDIS_URL to run Redis integration tests against a real server.")

        from redis.asyncio import Redis

        self.redis = Redis.from_url(redis_url, decode_responses=True)
        await self.redis.ping()
        self.prefix = f"cheat-clip-test-{uuid4().hex}"
        self.queue = RedisRenderQueue(self.redis, self.prefix)
        self.batch_id = uuid4().hex

    async def asyncTearDown(self):
        if not hasattr(self, "redis"):
            return

        async for key in self.redis.scan_iter(match=f"{self.prefix}:*"):
            await self.redis.delete(key)
        render_service.RENDER_BATCHES.pop(self.batch_id, None)
        render_service.BATCH_REQUESTS.pop(self.batch_id, None)
        await self.redis.aclose()

    async def test_enqueued_batch_is_restored_and_inflight_job_is_requeued(self):
        batch = {
            "batch_id": self.batch_id,
            "overall_status": "queued",
            "clips": [],
        }
        request = RenderBatchRequest(
            video_url="https://www.youtube.com/watch?v=test-video",
            video_id="test-video",
            clips=[],
            settings=RenderSettingsModel(),
        )

        await self.queue.enqueue(self.batch_id, batch, request, "render")
        claimed_job = await self.redis.brpoplpush(
            self.queue.queue_key,
            self.queue.processing_key,
            timeout=1,
        )
        self.assertIsNotNone(claimed_job)

        render_service.RENDER_BATCHES.pop(self.batch_id, None)
        render_service.BATCH_REQUESTS.pop(self.batch_id, None)
        restored_queue = RedisRenderQueue(self.redis, self.prefix)
        await restored_queue.restore()

        self.assertEqual(render_service.RENDER_BATCHES[self.batch_id], batch)
        self.assertEqual(render_service.BATCH_REQUESTS[self.batch_id], request)
        self.assertEqual(await self.redis.lrange(self.queue.processing_key, 0, -1), [])
        self.assertEqual(await self.redis.llen(self.queue.queue_key), 1)


if __name__ == "__main__":
    unittest.main()
