import asyncio
import os
import signal

from playwright.async_api import async_playwright


async def main():
    stopped = asyncio.Event()
    for sig in (signal.SIGTERM, signal.SIGINT):
        asyncio.get_running_loop().add_signal_handler(sig, stopped.set)

    data_dir = os.environ.get('DATA_DIR', '/data')
    async with async_playwright() as playwright:
        context = await playwright.chromium.launch_persistent_context(
            data_dir + '/browser', headless=False, viewport={'width': 1280, 'height': 900}
        )
        page = context.pages[0] if context.pages else await context.new_page()
        await page.goto('https://find.vivo.com.cn/', wait_until='domcontentloaded', timeout=60000)
        await stopped.wait()
        await context.close()


asyncio.run(main())
