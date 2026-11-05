"""HTTP liveness/readiness and resilient Telegram polling on 0.0.0.0:3000."""
import asyncio
import logging
import os
from aiohttp import web

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("photo_report_service")


def create_app():
    app = web.Application()
    app["service_state"] = {
        "service": "fotoreportcu-bot",
        "status": "starting" if os.getenv("BOT_TOKEN", "").strip() else "awaiting_bot_token",
        "telegram_connected": False,
    }

    async def status(request):
        return web.json_response(dict(request.app["service_state"]))

    async def ready(request):
        state = request.app["service_state"]
        return web.json_response(dict(state), status=200 if state["telegram_connected"] else 503)

    app.router.add_get("/", status)
    app.router.add_get("/health", status)
    app.router.add_get("/ready", ready)
    return app


async def run_bot(state):
    if not os.getenv("BOT_TOKEN", "").strip():
        log.warning("BOT_TOKEN is not configured; Telegram polling is disabled")
        state.update(status="awaiting_bot_token", telegram_connected=False)
        await asyncio.Event().wait()
        return
    try:
        import bot
        from aiogram.methods import GetUpdates
        from aiogram.exceptions import TelegramNetworkError, TelegramServerError
        from aiogram.client.session.middlewares.base import BaseRequestMiddleware

        class PollingStatusMiddleware(BaseRequestMiddleware):
            async def __call__(self, make_request, client, method):
                if not isinstance(method, GetUpdates):
                    return await make_request(client, method)
                try:
                    result = await make_request(client, method)
                except Exception as error:
                    state.update(telegram_connected=False, status="telegram_unavailable")
                    log.warning("Telegram polling failed: %s", type(error).__name__)
                    raise
                state.update(telegram_connected=True, status="running")
                return result

        bot.bot.session.middleware(PollingStatusMiddleware())
        try:
            delay = 2
            while True:
                state.update(status="connecting", telegram_connected=False)
                try:
                    await asyncio.wait_for(bot.bot.get_me(), timeout=20)
                    webhook = await asyncio.wait_for(bot.bot.get_webhook_info(), timeout=20)
                    if webhook.url:
                        state["status"] = "webhook_configured"
                        log.error("A webhook is configured; remove it explicitly before using polling")
                        return
                    log.info("Telegram authentication successful; starting polling")
                    await bot.dp.start_polling(bot.bot, handle_signals=False, close_bot_session=False)
                    state.update(status="stopped", telegram_connected=False)
                    return
                except (TelegramNetworkError, TelegramServerError, OSError, asyncio.TimeoutError) as error:
                    state.update(status="telegram_unavailable", telegram_connected=False)
                    log.warning("Telegram temporarily unavailable (%s); retry in %ss", type(error).__name__, delay)
                    await asyncio.sleep(delay)
                    delay = min(delay * 2, 60)
        finally:
            try:
                await bot.dp.storage.close()
            finally:
                await bot.bot.session.close()
    except asyncio.CancelledError:
        raise
    except Exception as error:
        state["status"] = "startup_failed"
        log.error("Telegram startup failed: %s", type(error).__name__)
    finally:
        state["telegram_connected"] = False
        if state["status"] in ("running", "connecting"):
            state["status"] = "stopped"


async def main():
    app = create_app()
    runner = web.AppRunner(app)
    await runner.setup()
    await web.TCPSite(runner, "0.0.0.0", 3000).start()
    log.info("HTTP status server listening on 0.0.0.0:3000")
    task = asyncio.create_task(run_bot(app["service_state"]))
    try:
        await asyncio.Event().wait()
    finally:
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)
        await runner.cleanup()


if __name__ == "__main__":
    asyncio.run(main())
