import asyncio
import json
import os
import signal
from pathlib import Path
import time
import urllib.parse
import urllib.request
from datetime import datetime

from playwright.async_api import async_playwright


DATA = Path(os.environ.get('DATA_DIR', '/data'))
URL = 'https://cloud.huawei.com/webFindPhone.html#/home'
DEVICE_NAME = os.environ.get('HUAWEI_DEVICE_NAME', '').strip()
PERSON_LABEL = os.environ.get('HUAWEI_NOTIFICATION_LABEL', '家人').strip()
CONTACTS_LABEL = os.environ.get('HUAWEI_CONTACTS_LABEL', 'Contacts').strip()
SHARING_TEXT = os.environ.get('HUAWEI_SHARING_TEXT', 'Sharing the location of 1 devices').strip()
KEEPALIVE_SECONDS = int(os.environ.get('HUAWEI_KEEPALIVE_SECONDS', '600'))
LOGIN_MARKERS = ('LOG IN', '扫码登录', '密码登录', '登录华为账号', 'HUAWEI Mobile Cloud')


def parse_schedules(value):
    result = set()
    for item in value.split(','):
        hour, minute = item.strip().split(':', 1)
        result.add((int(hour), int(minute)))
    return result


SCHEDULES = parse_schedules(os.environ.get('HUAWEI_REPORT_TIMES', '09:30,21:00'))


def send(title, body):
    key = os.environ['SERVERCHAN_SENDKEY'].strip()
    if not key.startswith('SCT') or not key.isalnum():
        raise ValueError('Invalid SendKey')
    request = urllib.request.Request('https://sctapi.ftqq.com/' + key + '.send', data=urllib.parse.urlencode({'title': title, 'desp': body}).encode())
    with urllib.request.urlopen(request, timeout=20) as response:
        result = json.load(response)
    if result.get('code') != 0:
        raise RuntimeError('Notification rejected')


async def open_find_phone(page, refresh=False):
    if 'webFindPhone' in page.url and refresh:
        await page.reload(wait_until='domcontentloaded', timeout=60000)
    elif 'webFindPhone' not in page.url:
        await page.goto(URL, wait_until='domcontentloaded', timeout=60000)
    await page.wait_for_timeout(3000)
    text = (await page.locator('body').inner_text(timeout=10000))[:5000]
    if 'webFindPhone' not in page.url or any(marker in text for marker in LOGIN_MARKERS):
        raise PermissionError('华为登录失效')


async def save_session(page):
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


async def keep_alive(page):
    await open_find_phone(page, refresh=True)
    await page.locator(f'span[title="{CONTACTS_LABEL}"]').first.wait_for(state='visible', timeout=45000)
    await save_session(page)


async def read_device(page):
    await open_find_phone(page, refresh=True)
    card = page.locator(f'.operation[aria-label="{DEVICE_NAME}"]').first
    if not await card.is_visible():
        contacts = page.locator(f'span[title="{CONTACTS_LABEL}"]').first
        await contacts.wait_for(state='visible', timeout=45000)
        await contacts.evaluate('(element) => element.click()')
        candidates = page.get_by_text(DEVICE_NAME, exact=True)
        if await candidates.count() == 0 or not any(
            [await candidates.nth(index).is_visible() for index in range(await candidates.count())]
        ):
            sharing = page.get_by_text(SHARING_TEXT, exact=True).first
            await sharing.wait_for(state='visible', timeout=20000)
            await sharing.evaluate('(element) => element.click()')
        await candidates.first.wait_for(state='attached', timeout=20000)
        device = None
        for index in range(await candidates.count()):
            candidate = candidates.nth(index)
            if await candidate.is_visible():
                device = candidate
                break
        if device is None:
            raise RuntimeError(f'联系人列表中的 {DEVICE_NAME} 卡片不可见')
        await device.evaluate('(element) => element.click()')
    try:
        await card.wait_for(state='visible', timeout=45000)
    except Exception:
        text = (await page.locator('body').inner_text(timeout=5000))[:5000]
        if 'webFindPhone' not in page.url or any(marker in text for marker in LOGIN_MARKERS):
            raise PermissionError('华为登录失效')
        raise RuntimeError(f'未找到 {DEVICE_NAME}，设备列表或页面结构可能变化')
    await card.click(timeout=30000)
    deadline = asyncio.get_running_loop().time() + 90
    latest = None
    while asyncio.get_running_loop().time() < deadline:
        address = (await card.locator('.offLineInfo').first.inner_text(timeout=10000)).strip()
        battery = (await card.locator('.batteryPower').first.inner_text(timeout=10000)).strip()
        status = (await card.locator('.device_status').first.inner_text(timeout=10000)).strip()
        updated = (await card.locator('.updateTime').first.inner_text(timeout=10000)).strip()
        latest = {'address': address, 'battery': battery, 'status': status, 'updated': updated}
        if address and battery and not any(x in updated.lower() for x in ('locating', '定位中')):
            await save_session(page)
            return latest
        await page.wait_for_timeout(3000)
    if latest and latest.get('address'):
        return latest
    raise RuntimeError('华为页面未返回位置')


async def report(page):
    stamp = datetime.now().astimezone().isoformat(timespec='seconds')
    try:
        device = await read_device(page)
    except PermissionError:
        title = f'{PERSON_LABEL}·华为登录失效'
        body = f'检查时间：{stamp}\n\n服务器上的华为账号需要重新登录验证。'
    except Exception as exc:
        print(type(exc).__name__ + ': ' + str(exc)[:300], flush=True)
        title = f'{PERSON_LABEL}·位置获取失败'
        body = f'检查时间：{stamp}\n\n未能读取 {DEVICE_NAME} 的地址和电量。\n\n原因：{type(exc).__name__}'
    else:
        address = device['address'] or '地址未知'
        battery = device['battery'] or '未知'
        title = f'{PERSON_LABEL}·{address} 电量{battery}'
        body = f'检查时间：{stamp}\n\n设备：{DEVICE_NAME}\n\n地址：{address}\n\n电池电量：{battery}\n\n设备状态：{device["status"] or "未知"}\n\n华为更新时间：{device["updated"] or "未知"}'
        (DATA / 'last.json').write_text(json.dumps(device, ensure_ascii=False), encoding='utf-8')
    await asyncio.to_thread(send, title, body)
    print(stamp + ' ' + title, flush=True)


def load_slots():
    try:
        return set(json.loads((DATA / 'sent-slots.json').read_text(encoding='utf-8')))
    except Exception:
        return set()


def save_slots(slots):
    cutoff = datetime.now().astimezone().date().isoformat()
    slots = {slot for slot in slots if slot >= cutoff}
    (DATA / 'sent-slots.json').write_text(json.dumps(sorted(slots)), encoding='utf-8')
    return slots


async def main():
    if not DEVICE_NAME:
        raise SystemExit('需要设置 HUAWEI_DEVICE_NAME')
    DATA.mkdir(parents=True, exist_ok=True)
    stopped = asyncio.Event()
    for sig in (signal.SIGTERM, signal.SIGINT):
        asyncio.get_running_loop().add_signal_handler(sig, stopped.set)
    slots = load_slots()
    last_keepalive = 0.0
    login_alerted = (DATA / 'login-alerted').exists()
    async with async_playwright() as pw:
        context = await pw.chromium.launch_persistent_context(str(DATA / 'browser'), headless=False, viewport={'width': 1280, 'height': 900})
        cookie_file = DATA / 'session-cookies.json'
        if cookie_file.exists():
            try:
                await context.add_cookies(json.loads(cookie_file.read_text(encoding='utf-8')))
            except Exception as exc:
                print('Cookie restore ' + type(exc).__name__ + ': ' + str(exc)[:300], flush=True)
        await context.add_init_script("""
            try {
              const saved = localStorage.getItem('__monitorSession');
              if (saved) {
                for (const [key, value] of Object.entries(JSON.parse(saved))) {
                  sessionStorage.setItem(key, value);
                }
              }
            } catch (_) {}
        """)
        page = context.pages[0] if context.pages else await context.new_page()
        if 'webFindPhone' not in page.url:
            await page.goto(URL, wait_until='domcontentloaded', timeout=60000)
        while not stopped.is_set():
            now = datetime.now().astimezone()
            monotonic_now = time.monotonic()
            if monotonic_now - last_keepalive >= KEEPALIVE_SECONDS:
                try:
                    await keep_alive(page)
                except PermissionError:
                    if not login_alerted:
                        stamp = now.isoformat(timespec='seconds')
                        alert_title = f'{PERSON_LABEL}·华为登录失效'
                        await asyncio.to_thread(send, alert_title, f'检查时间：{stamp}\n\n服务器上的华为账号需要重新登录验证。')
                        print(stamp + ' ' + alert_title, flush=True)
                        (DATA / 'login-alerted').write_text(stamp, encoding='utf-8')
                        login_alerted = True
                except Exception as exc:
                    print('Keepalive ' + type(exc).__name__ + ': ' + str(exc)[:300], flush=True)
                else:
                    (DATA / 'login-alerted').unlink(missing_ok=True)
                    login_alerted = False
                last_keepalive = monotonic_now
            slot = f'{now.date().isoformat()}-{now.hour:02d}:{now.minute:02d}'
            run_file = DATA / 'run.request'
            scheduled = (now.hour, now.minute) in SCHEDULES and slot not in slots
            manual = run_file.exists()
            if manual:
                run_file.unlink()
            if scheduled or manual:
                await report(page)
                if scheduled:
                    slots.add(slot)
                    slots = save_slots(slots)
            try:
                await asyncio.wait_for(stopped.wait(), timeout=15)
            except asyncio.TimeoutError:
                pass
        await context.close()


if __name__ == '__main__':
    asyncio.run(main())
