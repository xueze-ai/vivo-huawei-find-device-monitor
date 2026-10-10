import asyncio
import sqlite3
import time
import unittest
from unittest.mock import patch
import monitor


class QueueTests(unittest.IsolatedAsyncioTestCase):
    async def test_failed_delivery_is_removed_and_charged(self):
        db = sqlite3.connect(':memory:')
        db.execute('CREATE TABLE outbox (id INTEGER PRIMARY KEY,title TEXT,body TEXT,attempts INTEGER DEFAULT 0,next_at REAL DEFAULT 0,created REAL)')
        db.execute('CREATE TABLE quota(day TEXT PRIMARY KEY,used INTEGER NOT NULL)')
        db.execute('INSERT INTO outbox(title,body,created) VALUES (?,?,?)', ('test', 'body', time.time()))
        db.commit()
        async def stop(_):
            raise asyncio.CancelledError()
        with patch.object(monitor, 'send', side_effect=RuntimeError('network')), patch.object(monitor.asyncio, 'sleep', stop):
            with self.assertRaises(asyncio.CancelledError):
                await monitor.notifications(db)
        self.assertEqual(db.execute('SELECT count(*) FROM outbox').fetchone()[0], 0)
        self.assertEqual(db.execute('SELECT used FROM quota').fetchone()[0], 1)
        db.close()


if __name__ == '__main__':
    unittest.main()
