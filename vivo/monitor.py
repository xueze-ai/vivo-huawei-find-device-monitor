import asyncio
import json
import os
import signal
from pathlib import Path
import sqlite3
import time
import urllib.parse
import urllib.request
from datetime import datetime
from contextlib import AsyncExitStack
from core import distance, evaluate

DATA = Path(os.environ.get('DATA_DIR', '/data'))


class LoginRequired(Exception):
    pass


def database():
    DATA.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(DATA / 'monitor.sqlite')
    db.execute('PRAGMA journal_mode=WAL')
    db.execute('CREATE TABLE IF NOT EXISTS state (id INTEGER PRIMARY KEY, value TEXT)')
    db.execute('CREATE TABLE IF NOT EXISTS outbox (id INTEGER PRIMARY KEY, title TEXT, body TEXT, attempts INTEGER DEFAULT 0, next_at REAL DEFAULT 0, created REAL)')
    db.execute('CREATE TABLE IF NOT EXISTS quota (day TEXT PRIMARY KEY, used INTEGER NOT NULL)')
    return db


def send(title, body):
    key = os.environ['SERVERCHAN_SENDKEY'].strip()
    if not key.startswith('SCT') or not key.isalnum():
        raise ValueError('Invalid SendKey')
    request = urllib.request.Request('https://sctapi.ftqq.com/' + key + '.send', data=urllib.parse.urlencode({'title': title, 'desp': body}).encode())
    with urllib.request.urlopen(request, timeout=20) as response:
        result = json.load(response)
    if result.get('code') != 0:
        raise RuntimeError('Notification rejected')


async def notifications(db):
    while True:
        now = time.time()
        day = datetime.now().astimezone().strftime('%Y-%m-%d')
        with db:
            db.execute('DELETE FROM outbox WHERE created<?', (now - 86400,))
            db.execute('DELETE FROM quota WHERE day<?', (day,))
        quota = db.execute('SELECT used FROM quota WHERE day=?', (day,)).fetchone()
        if quota and quota[0] >= 900:
            await asyncio.sleep(60)
            continue
        row = db.execute('SELECT id,title,body,attempts,created FROM outbox WHERE next_at<=? ORDER BY id LIMIT 1', (time.time(),)).fetchone()
        if row:
            ident, title, body, attempts, created = row
            with db:
                db.execute('INSERT INTO quota(day,used) VALUES (?,1) ON CONFLICT(day) DO UPDATE SET used=used+1', (day,))
            try:
                await asyncio.to_thread(send, title, body)
            except Exception:
                # Never log exceptions containing a credential-bearing request URL.
                with db:
                    db.execute('UPDATE outbox SET attempts=attempts+1,next_at=? WHERE id=?', (time.time() + min(3600, 60 * 2**min(attempts, 6)), ident))
                print('通知发送失败，已安排重试', flush=True)
            else:
                with db:
                    db.execute('DELETE FROM outbox WHERE id=?', (ident,))
        await asyncio.sleep(5)


async def read_fix(page, cfg, previous_timestamp=0):
    from playwright.async_api import TimeoutError as PlaywrightTimeoutError

    adapter = cfg['adapter']
    await page.goto(cfg['url'], wait_until='domcontentloaded', timeout=45000)
    if cfg.get('share_member_name'):
        member = page.locator('.family-item', has_text=cfg['share_member_name'])
        try:
            await member.first.wait_for(state='visible', timeout=30000)
        except PlaywrightTimeoutError as exc:
            url = page.url.lower()
            try:
                text = (await page.locator('body').inner_text(timeout=5000))[:5000]
            except Exception:
                text = ''
            login_markers = ('扫码登录', '账号登录', '验证码登录', '请登录', '重新登录')
            if any(x in url for x in ('login', 'passport', 'oauth')) or any(x in text for x in login_markers):
                raise LoginRequired('vivo 登录已失效') from exc
            raise RuntimeError('共享成员入口没有出现，页面可能已改变') from exc
        await member.first.click(timeout=30000)
        await page.locator('.share-detail').wait_for(timeout=30000)
    for selector in adapter['click_selectors']:
        await page.locator(selector).click(timeout=20000)
    await page.locator(adapter['ready_selector']).wait_for(timeout=60000)
    # This script is a local, reviewed adapter, not script read from the website.
    script = Path(adapter['extract_script']).read_text(encoding='utf-8')
    deadline = time.monotonic() + cfg.get('location_wait_seconds', 60)
    while True:
        fix = await page.evaluate(script, cfg['device_id'])
        if fix and fix.get('timestamp', 0) > previous_timestamp and time.time() - fix['timestamp'] <= cfg['max_age_seconds']:
            return fix
        if time.monotonic() >= deadline:
            if fix:
                return fix
            raise RuntimeError('页面没有定位结果')
        await asyncio.sleep(3)


def report_due(state, cfg, now):
    return now - float(state.get('last_report_at', 0)) >= cfg.get('report_interval_seconds', 1800)


def motion_title(anchor, fix, threshold):
    if not anchor:
        return '位置汇报', None
    meters = distance(anchor, fix)
    if meters < threshold:
        return f'未移动（偏差约 {meters:.0f} 米）', meters
    return f'移动约 {meters:.0f} 米', meters


def add_last_fix(body, state):
    fix = state.get('fix')
    if not fix:
        return body
    body += '\n\n最后有效定位：' + str(fix.get('address') or f"{fix['lat']}, {fix['lon']}")
    body += '\n\n定位时间：' + datetime.fromtimestamp(fix['timestamp']).astimezone().isoformat(timespec='seconds')
    return body


def queue(db, title, body):
    stamp = datetime.now().astimezone().isoformat(timespec='seconds')
    body = '检查时间：' + stamp + '\n\n' + body
    with db:
        db.execute('INSERT INTO outbox(title,body,created) VALUES (?,?,?)', (title, body, time.time()))
    print(stamp + ' ' + title, flush=True)


def notification_title(cfg, state, status):
    prefix = str(cfg.get('notification_prefix', '')).strip()
    if not prefix:
        return status
    fix = state.get('fix') or {}
    address = str(fix.get('address') or '地址未知').strip()
    return f'{prefix}·{address}·{status}'


async def main():
    from playwright.async_api import async_playwright
    cfg = json.loads(Path(os.environ.get('CONFIG', '/app/config.json')).read_text(encoding='utf-8'))
    if not cfg.get('adapter_verified'):
        raise SystemExit('页面适配尚未验证，拒绝启动正式监控。请完成页面适配和配置。')
    if (not cfg.get('zones') and not cfg.get('allow_pending_geofences')) or not cfg.get('device_id') or not cfg['adapter']['ready_selector']:
        raise SystemExit('需要配置围栏和页面元素')
    if not os.environ.get('SERVERCHAN_SENDKEY'):
        raise SystemExit('需要配置 SERVERCHAN_SENDKEY')
    db = database()
    sender = asyncio.create_task(notifications(db))
    current = asyncio.current_task()
    for sig in (signal.SIGTERM, signal.SIGINT):
        asyncio.get_running_loop().add_signal_handler(sig, current.cancel)
    context = None
    try:
        async with async_playwright() as pw, AsyncExitStack() as cleanup:
            async def close_browser():
                if context:
                    try:
                        await context.close()
                    except Exception:
                        pass
            cleanup.push_async_callback(close_browser)
            context = None
            failures = 0
            while True:
                started = time.monotonic()
                now = time.time()
                row = db.execute('SELECT value FROM state WHERE id=1').fetchone()
                state = json.loads(row[0]) if row else {}
                previous_status = state.get('source_status')
                due = report_due(state, cfg, now)
                title = body = None
                try:
                    if context is None:
                        context = await pw.chromium.launch_persistent_context(str(DATA / 'browser'), headless=False, viewport={'width': 1280, 'height': 900})
                    page = context.pages[0] if context.pages else await context.new_page()
                    old_state = dict(state)
                    fix = await asyncio.wait_for(read_fix(page, cfg, state.get('fix', {}).get('timestamp', 0)), timeout=150)
                    state, eval_title, detail = evaluate(fix, state, cfg)
                    failures = 0

                    if eval_title == '手机离线或定位未更新':
                        state['source_status'] = 'stale'
                        if previous_status != 'stale' or due:
                            title = '手机离线或定位未更新'
                            body = add_last_fix(detail, state)
                            state['last_report_at'] = now
                    else:
                        state['source_status'] = 'ok'
                        event = eval_title if eval_title != '定位更新' else None
                        recovered = previous_status in ('stale', 'login', 'error')
                        if event or due or recovered:
                            report_title, meters = motion_title(
                                old_state.get('report_fix') or old_state.get('fix'),
                                fix,
                                cfg['movement_meters'],
                            )
                            parts = []
                            if event:
                                parts.append(event)
                            if recovered:
                                parts.append('定位已恢复')
                            parts.append(report_title)
                            title = '；'.join(parts)
                            body = add_last_fix(detail, state)
                            if due or recovered:
                                state['last_report_at'] = now
                                state['report_fix'] = fix
                except LoginRequired:
                    failures = 0
                    state['source_status'] = 'login'
                    if previous_status != 'login' or due:
                        title = 'vivo 登录失效'
                        body = add_last_fix('服务器上的 vivo 登录状态已失效，需要重新登录验证。', state)
                        state['last_report_at'] = now
                    if context:
                        try:
                            await context.close()
                        except Exception:
                            pass
                        context = None
                except Exception as exc:
                    failures += 1
                    state['source_status'] = 'error'
                    if previous_status != 'error' or due:
                        title = '定位监控异常'
                        body = add_last_fix('页面没有正常完成定位检查。可能是网络故障、页面结构变化或浏览器异常。', state)
                        state['last_report_at'] = now
                    print(type(exc).__name__ + ': ' + str(exc)[:200], flush=True)
                    if context:
                        try:
                            await context.close()
                        except Exception:
                            pass
                        context = None
                with db:
                    db.execute('INSERT OR REPLACE INTO state VALUES (1,?)', (json.dumps(state, ensure_ascii=False),))
                if title:
                    queue(db, notification_title(cfg, state, title), body)
                (DATA / 'heartbeat').write_text(str(time.time()))
                if sender.done():
                    raise RuntimeError('通知工作进程停止，需要重启')
                if failures >= 3:
                    await asyncio.sleep(10)
                    raise RuntimeError('连续三轮定位错误，重建运行环境')
                await asyncio.sleep(max(1, cfg['interval_seconds'] - (time.monotonic() - started)))
    finally:
        sender.cancel()
        await asyncio.gather(sender, return_exceptions=True)
        db.close()


if __name__ == '__main__':
    asyncio.run(main())
