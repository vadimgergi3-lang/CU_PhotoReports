"""Offline startup, HTTP readiness and real DOCX smoke tests."""
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from aiohttp.test_utils import TestClient, TestServer
from docx import Document
from PIL import Image
import app
import config
from docgen import build_slots, generate_report


class StartupTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        with patch.dict(os.environ, {"BOT_TOKEN": ""}):
            self.application = app.create_app()
        self.client = TestClient(TestServer(self.application))
        await self.client.start_server()

    async def asyncTearDown(self):
        await self.client.close()

    async def test_health_without_token(self):
        response = await self.client.get("/health")
        self.assertEqual(response.status, 200)
        self.assertEqual((await response.json())["status"], "awaiting_bot_token")

    async def test_readiness_without_connection(self):
        response = await self.client.get("/ready")
        self.assertEqual(response.status, 503)
        self.assertFalse((await response.json())["telegram_connected"])

    async def test_readiness_connected(self):
        self.application["service_state"].update(status="running", telegram_connected=True)
        response = await self.client.get("/ready")
        self.assertEqual(response.status, 200)

    async def test_invalid_token_does_not_crash_http(self):
        with patch.dict(os.environ, {"BOT_TOKEN": "invalid"}):
            await app.run_bot(self.application["service_state"])
        self.assertEqual(self.application["service_state"]["status"], "startup_failed")
        self.assertEqual((await self.client.get("/health")).status, 200)
        self.assertEqual((await self.client.get("/ready")).status, 503)


class DocumentTests(unittest.TestCase):
    def test_all_templates_generate_docx_with_photo(self):
        with tempfile.TemporaryDirectory() as directory:
            photo = str(Path(directory) / "sample.jpg")
            Image.new("RGB", (800, 600), "white").save(photo)
            for key, template in config.TEMPLATES.items():
                with self.subTest(template=key):
                    slots = build_slots(template, ["TEST1234567"])
                    self.assertTrue(slots)
                    output = str(Path(directory) / (key + ".docx"))
                    generate_report(template, template["meta"].copy(), ["TEST1234567"],
                                    {slots[0]["id"]: photo}, output)
                    document = Document(output)
                    self.assertTrue(document.tables)
                    self.assertGreater(Path(output).stat().st_size, 1000)
