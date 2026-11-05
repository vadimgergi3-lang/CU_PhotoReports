"""Regression tests for startup retries, bounded images and restart identity."""
import asyncio
import os
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

from PIL import Image
from docgen import _prepare_photo
import app


class PhotoTests(unittest.TestCase):
    def test_large_photo_is_bounded_and_rgb(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "large.png"
            Image.new("RGBA", (2000, 3000), (10, 20, 30, 255)).save(source)
            result = _prepare_photo(source)
            try:
                with Image.open(result) as image:
                    self.assertEqual(image.mode, "RGB")
                    self.assertEqual(image.width, 1200)
                    self.assertLess(image.height, 1200)
            finally:
                os.unlink(result)


class RetryTests(unittest.IsolatedAsyncioTestCase):
    async def test_transient_auth_failure_retries_and_closes(self):
        fake = types.SimpleNamespace()
        fake.bot = MagicMock()
        fake.bot.get_me = AsyncMock(side_effect=[asyncio.TimeoutError(), object()])
        fake.bot.get_webhook_info = AsyncMock(return_value=types.SimpleNamespace(url=""))
        fake.bot.session.close = AsyncMock()
        fake.dp = MagicMock()
        fake.dp.start_polling = AsyncMock()
        fake.dp.storage.close = AsyncMock()
        state = {"status": "starting", "telegram_connected": False}
        with patch.dict(os.environ, {"BOT_TOKEN": "test"}), patch.dict(sys.modules, {"bot": fake}), patch("app.asyncio.sleep", new_callable=AsyncMock) as sleep:
            await app.run_bot(state)
        self.assertEqual(fake.bot.get_me.await_count, 2)
        sleep.assert_awaited_once_with(2)
        fake.dp.start_polling.assert_awaited_once()
        fake.dp.storage.close.assert_awaited_once()
        fake.bot.session.close.assert_awaited_once()
        self.assertFalse(state["telegram_connected"])

    async def test_webhook_does_not_start_conflicting_polling(self):
        fake = types.SimpleNamespace(bot=MagicMock(), dp=MagicMock())
        fake.bot.get_me = AsyncMock()
        fake.bot.get_webhook_info = AsyncMock(return_value=types.SimpleNamespace(url="https://example.org/hook"))
        fake.bot.session.close = AsyncMock()
        fake.dp.storage.close = AsyncMock()
        state = {"status": "starting", "telegram_connected": False}
        with patch.dict(os.environ, {"BOT_TOKEN": "test"}), patch.dict(sys.modules, {"bot": fake}):
            await app.run_bot(state)
        self.assertEqual(state["status"], "webhook_configured")
        fake.dp.start_polling.assert_not_called()
