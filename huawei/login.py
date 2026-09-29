import asyncio
import json
import os
import signal
from pathlib import Path

from playwright.async_api import async_playwright


DATA = Path(os.environ.get('DATA_DIR', '/data'))


async def save_session(page):
    try:
        await page.evaluate("""
            localStorage.setItem('__monitorSession', JSON.stringify(
              Object.fromEntries(Array.from({length: sessionStorage.length}, (_, i) => {
                const key = sessionStorage.key(i);
                return [key, sessionStorage.getItem(key)];
              }))
            ));
        """)
        cookies = await page.context.cookies()
        (DATA / 'session-cookies.json').write_text(
            json.dumps(cookies, ensure_ascii=False), encoding='utf-8'
        )
    except Exception:
        pass


async def main():
    stopped = asyncio.Event()
    for sig in (signal.SIGTERM, signal.SIGINT):
        asyncio.get_running_loop().add_signal_handler(sig, stopped.set)

    DATA.mkdir(parents=True, exist_ok=True)
    async with async_playwright() as playwright:
        context = await playwright.chromium.launch_persistent_context(
            str(DATA / 'browser'), headless=False, viewport={'width': 1280, 'height': 900}
        )
        page = context.pages[0] if context.pages else await context.new_page()
        await page.goto(
            'https://cloud.huawei.com/webFindPhone.html#/home',
            wait_until='domcontentloaded', timeout=60000,
        )
        while not stopped.is_set():
            await save_session(page)
            try:
                await asyncio.wait_for(stopped.wait(), timeout=2)
            except asyncio.TimeoutError:
                pass
        await context.close()


asyncio.run(main())
