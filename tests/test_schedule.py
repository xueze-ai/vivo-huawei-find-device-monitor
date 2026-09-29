import unittest
from datetime import datetime
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'vivo'))
from monitor import due_report_slot, mark_report_slot


class ScheduleTests(unittest.TestCase):
    def test_daily_slot_is_sent_once(self):
        config = {'report_times': ['09:00', '22:00'], 'report_grace_seconds': 900}
        now = datetime.fromisoformat('2026-09-29T09:05:00+08:00')
        state = {}
        slot = due_report_slot(state, config, now)
        self.assertEqual(slot, '2026-09-29-09:00')
        mark_report_slot(state, slot, now)
        self.assertIsNone(due_report_slot(state, config, now))

    def test_outside_delivery_window_is_not_due(self):
        config = {'report_times': ['09:00', '22:00'], 'report_grace_seconds': 900}
        now = datetime.fromisoformat('2026-09-29T09:16:00+08:00')
        self.assertIsNone(due_report_slot({}, config, now))


if __name__ == '__main__':
    unittest.main()
